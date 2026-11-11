import csv
import io
import json
import secrets
from functools import wraps
from datetime import timezone
from flask import Blueprint,current_app,g,jsonify,request,session,render_template,redirect,Response
from sqlalchemy import select,func,update,text
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from typing import Literal
from werkzeug.security import check_password_hash,generate_password_hash
from .db import User,Transaction,Case,AuditEvent,utcnow
from .schema import TransactionInput
from .scoring import score_transaction,serialize,Conflict
from .ml import drift_summary,metrics
from . import rate_allowed

web=Blueprint("web",__name__)
# Equalize missing-user password checking without storing a usable password.
DUMMY_HASH=generate_password_hash(secrets.token_urlsafe(32))


def factory():return current_app.extensions["db_factory"]
def model():return current_app.extensions["model_store"]


def admin(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        if not g.user or g.user.role!="admin":return jsonify(error="Administrator role required"),403
        return fn(*args,**kwargs)
    return wrapper


def validation_errors(exc):
    return [{"field":".".join(map(str,e["loc"])),"message":e["msg"]} for e in exc.errors()]


def requested_page():
    page=int(request.args.get("page",1))
    if not 1<=page<=1_000_000:
        raise ValueError("page is outside the supported range")
    return page


@web.get("/health/live")
def health():return jsonify(status="alive")


@web.get("/health/ready")
def ready():
    try:
        with factory()() as db:
            db.execute(select(User.id).limit(1))
            db.execute(select(Transaction.context).limit(1))
        limiter=current_app.extensions["rate_limiter"]
        if limiter.redis is not None:
            try:limiter.redis.ping()
            except Exception:return jsonify(status="unavailable",database="ready",rate_limiter="unavailable"),503
        ok=model().bundle is not None
        return jsonify(status="ready" if ok else "degraded",database="ready",model="ready" if ok else "unavailable"),200 if ok else 503
    except Exception:return jsonify(status="unavailable",database="unavailable"),503


@web.get("/login")
def login_page():
    if g.user:return redirect("/")
    return render_template("login.html")


@web.get("/api/csrf")
def csrf():return jsonify(csrf_token=session["csrf"])


class Credentials(BaseModel):
    model_config=ConfigDict(extra="forbid")
    username:str=Field(min_length=3,max_length=64,pattern=r"^[a-zA-Z0-9_.-]+$")
    password:str=Field(min_length=1,max_length=128)


@web.post("/api/login")
def login():
    try:data=Credentials.model_validate(request.get_json())
    except ValidationError as e:return jsonify(error="Invalid login fields",details=validation_errors(e)),422
    username=data.username.lower()
    if not rate_allowed("login-ip:"+(request.remote_addr or "unknown"),20,300) or not rate_allowed("login-user:"+username,8,300):
        return jsonify(error="Too many login attempts; try again in five minutes"),429
    with factory()() as db:
        user=db.scalar(select(User).where(User.username==username))
        valid=check_password_hash(user.password_hash if user else DUMMY_HASH,data.password)
        if not user or not valid or not user.active:
            db.add(AuditEvent(action="login.failed",target="authentication",details={}));db.commit()
            return jsonify(error="Invalid username or password"),401
        session.clear();session["user_id"]=user.id;session["csrf"]=secrets.token_urlsafe(32);session.permanent=True
        db.add(AuditEvent(actor_id=user.id,action="login.succeeded",target="authentication",details={}));db.commit()
        return jsonify(username=user.username,role=user.role,csrf_token=session["csrf"])


@web.post("/api/logout")
def logout():
    with factory()() as db:
        db.add(AuditEvent(actor_id=g.user.id,action="logout",target="authentication",details={}));db.commit()
    session.clear();return jsonify(status="signed_out")


@web.get("/")
def dashboard():return render_template("dashboard.html",user=g.user)


@web.post("/api/transactions")
def score():
    if not rate_allowed(f"score:{g.user.id}",current_app.config["SCORE_RATE_LIMIT"]):return jsonify(error="Request limit exceeded"),429
    try:
        result=score_transaction(factory(),model(),request.get_json(),g.user.id)
        return jsonify(result),200 if result["replayed"] else 201
    except ValidationError as e:return jsonify(error="Invalid transaction",details=validation_errors(e)),422
    except Conflict as e:return jsonify(error=str(e)),409


@web.post("/api/import")
@admin
def import_csv():
    if not rate_allowed(f"import:{g.user.id}",5,300):return jsonify(error="Import limit exceeded"),429
    upload=request.files.get("file")
    if not upload:return jsonify(error="Upload a UTF-8 CSV in the file field"),400
    try:
        content=upload.read().decode("utf-8-sig")
        reader=csv.DictReader(io.StringIO(content),strict=True)
        expected=set(TransactionInput.model_fields)
        required={k for k,v in TransactionInput.model_fields.items() if v.is_required()}
        supplied=set(reader.fieldnames or [])
        if not reader.fieldnames or len(reader.fieldnames)!=len(supplied) or not required.issubset(supplied) or not supplied.issubset(expected):
            return jsonify(error="CSV requires transaction fields; optional deprecated hints may be included. Labels and legacy CSV columns are not accepted.",expected_columns=sorted(expected)),422
        raw=[]
        for row in reader:
            raw.append(row)
            if len(raw)>current_app.config["MAX_IMPORT_ROWS"]:return jsonify(error="Maximum 1000 rows per import"),413
        if not raw:return jsonify(error="CSV contains no data rows"),422
        valid,errors=[],[]
        for i,row in enumerate(raw,2):
            try:valid.append((i,TransactionInput.model_validate(row).payload()))
            except ValidationError as e:errors.append({"row":i,"details":validation_errors(e)})
        if errors:return jsonify(error="CSV validation failed; no rows imported",errors=errors),422
    except (UnicodeDecodeError,csv.Error):return jsonify(error="Invalid UTF-8 CSV"),422
    results=[]
    for line,row in sorted(valid,key=lambda pair:pair[1]["timestamp"]):
        try:results.append({"row":line,**score_transaction(factory(),model(),row,g.user.id)})
        except Conflict as e:results.append({"row":line,"error":str(e)})
    with factory()() as db:
        db.add(AuditEvent(actor_id=g.user.id,action="import.completed",target="csv",
            details={"rows":len(results),"conflicts":sum("error" in r for r in results)}));db.commit()
    return jsonify(results=results,processed=len(results),conflicts=sum("error" in r for r in results))


@web.get("/api/transactions")
def transactions():
    decision=request.args.get("decision","");query=request.args.get("q","")[:64]
    try:page=requested_page()
    except ValueError:return jsonify(error="page must be an integer from 1 to 1000000"),422
    stmt=select(Transaction)
    if decision:
        if decision not in ("allow","review","decline"):return jsonify(error="Invalid decision filter"),422
        stmt=stmt.where(Transaction.decision==decision)
    if query:stmt=stmt.where(Transaction.transaction_id.contains(query,autoescape=True))
    with factory()() as db:
        total=db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows=db.scalars(stmt.order_by(Transaction.id.desc()).offset((page-1)*25).limit(25)).all()
        return jsonify(items=[serialize(r) for r in rows],total=total,page=page,page_size=25)


@web.get("/api/overview")
def overview():
    with factory()() as db:
        counts=dict(db.execute(select(Transaction.decision,func.count()).group_by(Transaction.decision)).all())
        total=sum(counts.values())
        open_cases=db.scalar(select(func.count()).select_from(Case).where(Case.status!="resolved"))
        recent=db.scalars(select(Transaction).order_by(Transaction.id.desc()).limit(500)).all()
        latencies=sorted(t.latency_ms for t in recent)
        p95=latencies[min(len(latencies)-1,int(len(latencies)*.95))] if latencies else 0
        return jsonify(total=total,counts=counts,open_cases=open_cases,p95_ms=round(p95,1),
                       model_status="ready" if model().bundle else "unavailable",
                       model_version=model().bundle["version"] if model().bundle else None,
                       review_threshold=model().bundle["threshold"] if model().bundle else None,
                       simulation=True)


def case_dict(case,tx):
    return {"id":case.id,"status":case.status,"outcome":case.outcome,"assigned_to":case.assigned_to,
            "notes":case.notes,"revision":case.revision,"updated_at":case.updated_at.isoformat(),
            "transaction":serialize(tx),"features":tx.features}


@web.get("/api/cases")
def cases():
    status=request.args.get("status","")
    if status and status not in ("open","investigating","resolved"):return jsonify(error="Invalid case status"),422
    stmt=select(Case,Transaction).join(Transaction,Case.transaction_id==Transaction.id)
    if status:stmt=stmt.where(Case.status==status)
    try:page=requested_page()
    except ValueError:return jsonify(error="page must be an integer from 1 to 1000000"),422
    with factory()() as db:
        total=db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows=db.execute(stmt.order_by(Transaction.score.desc().nullslast(),Case.id).offset((page-1)*25).limit(25)).all()
        return jsonify(items=[case_dict(c,t) for c,t in rows],total=total,page=page,page_size=25)


class CaseUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    revision:int=Field(ge=1)
    status:Literal["open","investigating","resolved"]
    outcome:Literal["fraud","legitimate","unresolved"]|None=None
    assigned_to:int|None=Field(default=None,ge=1)
    notes:str=Field(default="",max_length=4000)


@web.patch("/api/cases/<int:case_id>")
def update_case(case_id):
    try:data=CaseUpdate.model_validate(request.get_json())
    except ValidationError as e:return jsonify(error="Invalid case update",details=validation_errors(e)),422
    if data.status=="resolved" and data.outcome not in ("fraud","legitimate"):
        return jsonify(error="Resolve a case only with a confirmed fraud or legitimate outcome"),422
    if data.status!="resolved" and data.outcome in ("fraud","legitimate"):
        return jsonify(error="Confirmed outcomes require resolved status"),422
    with factory()() as db:
        case=db.get(Case,case_id)
        if not case:return jsonify(error="Case not found"),404
        if g.user.role!="admin" and (case.assigned_to not in (None,g.user.id) or data.assigned_to!=g.user.id):
            return jsonify(error="Analysts must claim their own case and cannot edit another analyst's assignment"),403
        if data.assigned_to is not None:
            assigned=db.get(User,data.assigned_to)
            if not assigned or not assigned.active:return jsonify(error="Assignee must be an active user"),422
        changes=data.model_dump(exclude={"revision"})
        old={k:getattr(case,k) for k in changes}
        n=db.execute(update(Case).where(Case.id==case_id,Case.revision==data.revision).values(**changes,revision=data.revision+1,updated_at=utcnow())).rowcount
        if not n:return jsonify(error="Case changed by another analyst; refresh before editing"),409
        db.add(AuditEvent(actor_id=g.user.id,action="case.updated",target=f"case:{case_id}",details={"before":old,"after":changes,"revision":data.revision+1}))
        db.commit();db.refresh(case)
        return jsonify(case_dict(case,db.get(Transaction,case.transaction_id)))


@web.get("/api/cases/<int:case_id>/history")
def case_history(case_id):
    with factory()() as db:
        if not db.get(Case,case_id):return jsonify(error="Case not found"),404
        events=db.scalars(select(AuditEvent).where(AuditEvent.target==f"case:{case_id}").order_by(AuditEvent.id)).all()
        return jsonify(items=[{"actor_id":e.actor_id,"action":e.action,"details":e.details,"time":e.created_at.isoformat()} for e in events])


@web.get("/api/users")
def users():
    with factory()() as db:
        rows=db.scalars(select(User).where(User.active==True)).all()
        return jsonify(items=[{"id":u.id,"username":u.username,"role":u.role} for u in rows],current_user_id=g.user.id)


@web.get("/api/model")
def model_info():
    if not model().report:return jsonify(status="unavailable"),503
    report={k:v for k,v in model().report.items() if k!="reference_features"}
    return jsonify(status="ready",report=report)


@web.get("/api/drift")
def drift():
    if not model().report:return jsonify(status="model_unavailable"),503
    with factory()() as db:
        recent=db.scalars(select(Transaction).where(Transaction.model_version==model().bundle["version"]).order_by(Transaction.id.desc()).limit(500)).all()
        return jsonify(drift_summary([t.features for t in recent],model().report["reference_features"]))


@web.get("/api/feedback.csv")
@admin
def feedback():
    from .feedback import FIELDS
    from .features import FEATURE_VERSION
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=FIELDS);writer.writeheader()
    with factory()() as db:
        rows=db.execute(select(Case,Transaction).join(Transaction,Case.transaction_id==Transaction.id).where(Case.status=="resolved")).all()
        count=0;skipped=0
        for c,t in rows:
            if (t.context or {}).get("feature_version")!=FEATURE_VERSION:
                skipped+=1;continue
            labelled=c.updated_at
            if labelled.tzinfo is None:labelled=labelled.replace(tzinfo=timezone.utc)
            writer.writerow(dict(transaction_json=json.dumps(t.payload,sort_keys=True),
                features_json=json.dumps(t.features,sort_keys=True),feature_version=FEATURE_VERSION,
                fraud_label=int(c.outcome=="fraud"),label_available_at=labelled.isoformat(),source="analyst_review"))
            count+=1
        db.add(AuditEvent(actor_id=g.user.id,action="feedback.exported",target="feedback",details={"rows":count,"skipped_legacy":skipped}));db.commit()
    return Response(out.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=reviewed_feedback.csv","X-Skipped-Legacy-Rows":str(skipped)})


@web.get("/api/transactions/<transaction_id>/explanation")
def explanation(transaction_id):
    if not rate_allowed(f"explain:{g.user.id}",30):return jsonify(error="Explanation request limit exceeded"),429
    from .ml import ModelStore
    from .explanations import explain
    with factory()() as db:
        tx=db.scalar(select(Transaction).where(Transaction.transaction_id==transaction_id))
        if not tx:return jsonify(error="Transaction not found"),404
        store=model() if model().bundle and tx.model_version==model().bundle["version"] else ModelStore(current_app.config["ARTIFACT_ROOT"],tx.model_version)
        if not store.bundle:return jsonify(error="Original compatible model artifact unavailable; no substitute explanation generated"),409
        try:return jsonify(explain(store.bundle,tx.features))
        except Exception:return jsonify(error="Model attribution unavailable"),503


@web.post("/api/transactions/<transaction_id>/review")
def manual_review(transaction_id):
    from .scoring import lock_payer
    with factory()() as db:
        lock_payer(db,"case:"+transaction_id)
        tx=db.scalar(select(Transaction).where(Transaction.transaction_id==transaction_id))
        if not tx:return jsonify(error="Transaction not found"),404
        case=db.scalar(select(Case).where(Case.transaction_id==tx.id))
        if not case:
            case=Case(transaction_id=tx.id);db.add(case);db.flush()
            db.add(AuditEvent(actor_id=g.user.id,action="case.manually_opened",target=f"case:{case.id}",details={"transaction_id":transaction_id}))
            db.commit()
        return jsonify(case_dict(case,tx))


@web.get("/api/capacity")
def capacity():
    with factory()() as db:
        pending=db.scalar(select(func.count()).select_from(Case).where(Case.status!="resolved"))
        daily=current_app.config["REVIEW_CAPACITY_PER_DAY"]
        return jsonify(pending=pending,planned_reviews_per_day=daily,
            backlog_days=round(pending/max(daily,1),2),over_capacity=pending>daily,
            validation_alert_budget=model().bundle.get("review_budget") if model().bundle else None,
            note="Queue retains every recommendation. Budget is an operating-point target, not a hard admission cap; backlog requires staffing or policy review.")


@web.get("/api/sample.csv")
@admin
def sample_csv():
    from pathlib import Path
    from flask import send_file
    return send_file(Path(__file__).resolve().parent.parent/"data"/"sample_import.csv",as_attachment=True,download_name="sample_import.csv")


@web.get("/api/audit")
@admin
def audit():
    with factory()() as db:
        rows=db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(100)).all()
        return jsonify(items=[{"id":e.id,"action":e.action,"target":e.target,"actor_id":e.actor_id,"time":e.created_at.isoformat()} for e in rows])
