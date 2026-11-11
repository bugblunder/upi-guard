"""Operator commands. Training and model activation are explicit offline actions."""
import argparse
import csv
import getpass
import json
import os
import re
from pathlib import Path
from sqlalchemy import select
from werkzeug.security import generate_password_hash
from .simulator import generate_transactions,write_csv


def add_user(app,username,role,password):
    from .db import User,AuditEvent
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{3,64}",username):raise ValueError("Username: 3–64 letters, numbers, dots, underscores or hyphens")
    if len(password)<12 or len(password)>128:raise ValueError("Password must be 12–128 characters")
    with app.extensions["db_factory"]() as db:
        if db.scalar(select(User).where(User.username==username.lower())):raise ValueError("User already exists")
        user=User(username=username.lower(),password_hash=generate_password_hash(password),role=role)
        db.add(user);db.flush();db.add(AuditEvent(actor_id=user.id,action="user.created",target=f"user:{user.id}",details={"role":role}));db.commit()


def main():
    p=argparse.ArgumentParser(description="UPI Guard v2 — synthetic fraud-risk sandbox")
    sub=p.add_subparsers(dest="command",required=True)
    init=sub.add_parser("init",help="Create schema and first admin");init.add_argument("--username",default="admin")
    user=sub.add_parser("add-user");user.add_argument("username");user.add_argument("--role",choices=["admin","analyst"],default="analyst")
    sim=sub.add_parser("simulate");sim.add_argument("--count",type=int,default=12000);sim.add_argument("--seed",type=int,default=42);sim.add_argument("--output",default="data/generated.csv");sim.add_argument("--unlabelled",action="store_true")
    train=sub.add_parser("train");train.add_argument("--input",default="data/synthetic_training.csv");train.add_argument("--artifacts",default="artifacts");train.add_argument("--seed",type=int,default=42)
    train.add_argument("--review-budget",type=float,default=.02);train.add_argument("--activate",action="store_true")
    merge=sub.add_parser("merge-feedback");merge.add_argument("--base",required=True);merge.add_argument("--feedback",required=True);merge.add_argument("--output",required=True)
    snap=sub.add_parser("train-snapshot");snap.add_argument("--input",required=True);snap.add_argument("--artifacts",default="artifacts");snap.add_argument("--seed",type=int,default=42);snap.add_argument("--review-budget",type=float,default=.02)
    demo=sub.add_parser("demo");demo.add_argument("--count",type=int,default=300);demo.add_argument("--seed",type=int,default=99);demo.add_argument("--username",default="admin")
    serve=sub.add_parser("serve");serve.add_argument("--port",type=int,default=5000)
    activate=sub.add_parser("activate");activate.add_argument("version");activate.add_argument("--artifacts",default="artifacts")
    sub.add_parser("check",help="Check model, schema and readiness")
    sub.add_parser("migrate",help="Apply database migrations")
    args=p.parse_args()
    if args.command=="merge-feedback":
        from .feedback import merge_feedback
        print(json.dumps(merge_feedback(args.base,args.feedback,args.output),indent=2));return
    if args.command=="train-snapshot":
        from .feedback import train_snapshot
        result=train_snapshot(args.input,args.artifacts,args.seed,args.review_budget)
        print(json.dumps({"candidate_version":result["version"],"activated":False},indent=2));return
    if args.command=="simulate":
        if not 10<=args.count<=100000:raise ValueError("Use 10–100000 events")
        write_csv(generate_transactions(args.count,args.seed),args.output,labelled=not args.unlabelled)
        print(f"Wrote {args.count} synthetic events to {args.output}");return
    if args.command=="train":
        from .schema import TransactionInput
        from .ml import train
        with open(args.input,newline="",encoding="utf-8-sig") as f:rows=list(csv.DictReader(f))
        for row in rows:
            TransactionInput.model_validate({k:v for k,v in row.items() if k not in ("fraud_label","scenario")})
            if str(row.get("fraud_label")) not in ("0","1"):raise ValueError("fraud_label must be 0 or 1")
        result=train(rows,args.artifacts,args.seed,review_budget=args.review_budget,activate=args.activate)
        print(json.dumps({"version":result["version"],"selected":result["selected_model"],"test":result["models"][result["selected_model"]]["test"]},indent=2));return
    if args.command=="activate":
        from .ml import atomic_json, ModelStore
        root=Path(args.artifacts)
        candidate=ModelStore(root, args.version)
        if candidate.bundle is None:raise ValueError("Candidate validation failed: " + candidate.error)
        atomic_json(root/"active.json",{"version":args.version})
        print("Activated",args.version,"— restart every application worker to load this version.");return
    from . import create_app
    app=create_app()
    if args.command=="migrate":
        from .db import migrate
        migrate(app.config['DATABASE_URL']);print('Database migrations applied.');return
    if args.command in ("init","add-user"):
        from .db import migrate
        migrate(app.config['DATABASE_URL'])
        password=os.getenv("GUARD_ADMIN_PASSWORD") if args.command=="init" else os.getenv("GUARD_USER_PASSWORD")
        if not password:
            password=getpass.getpass("New password (12+ characters): ")
            if password!=getpass.getpass("Confirm password: "):raise ValueError("Passwords do not match")
        add_user(app,args.username,"admin" if args.command=="init" else args.role,password)
        print("Account created. Passwords are stored as scrypt hashes.")
    elif args.command=="demo":
        from .db import User
        from .scoring import score_transaction
        if not 10<=args.count<=12000:raise ValueError("Use 10–12000 demo events")
        with app.extensions["db_factory"]() as db:
            user=db.scalar(select(User).where(User.username==args.username))
            if not user:raise ValueError("Initialize an administrator first")
            if user.role!="admin":raise ValueError("Demo loading requires an administrator")
            actor=user.id
        counts={"allow":0,"review":0,"decline":0,"replayed":0}
        for row in generate_transactions(args.count,args.seed):
            row={k:v for k,v in row.items() if k not in ("fraud_label","scenario")}
            result=score_transaction(app.extensions["db_factory"],app.extensions["model_store"],row,actor)
            counts[result["decision"]]+=1;counts["replayed"]+=int(result["replayed"])
        print(json.dumps(counts,indent=2))
    elif args.command=="check":
        with app.test_client() as client:
            r=client.get("/health/ready");print(json.dumps(r.json,indent=2));raise SystemExit(0 if r.status_code==200 else 1)
    elif args.command=="serve":
        if os.getenv("APP_ENV")=="production":raise ValueError("Use gunicorn in production")
        app.run(host="127.0.0.1",port=args.port,debug=False)


if __name__=="__main__":
    try:main()
    except (ValueError,FileExistsError) as exc:raise SystemExit(str(exc))
