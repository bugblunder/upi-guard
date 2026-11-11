"""UPI Guard v2 application factory."""
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
# Small tabular requests do not benefit from one OpenMP team per web worker.
# Operators can explicitly override this before process startup.
os.environ.setdefault("OMP_NUM_THREADS", "1")
from datetime import timedelta
from pathlib import Path
from flask import Flask, g, request, session, jsonify, redirect, url_for
from sqlalchemy import select, func, delete, text
from werkzeug.exceptions import HTTPException
from .db import connect, User
from .limiting import Limiter, TrustedProxy
from .ml import ModelStore


def create_app(config=None):
    root=Path(__file__).resolve().parent.parent
    app=Flask(__name__)
    production=os.getenv("APP_ENV","development")=="production"
    instance=Path(os.getenv("INSTANCE_PATH",str(root/"instance"))).resolve()
    instance.mkdir(parents=True,exist_ok=True)
    secret=os.getenv("SECRET_KEY")
    if config and config.get("SECRET_KEY"): secret=config["SECRET_KEY"]
    if not secret:
        if production: raise RuntimeError("SECRET_KEY is required in production")
        secret_file=instance/"secret.key"
        if not secret_file.exists():
            try:
                fd=os.open(secret_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,"w") as f:f.write(secrets.token_hex(32))
            except FileExistsError:pass
        secret=secret_file.read_text().strip()
    if len(secret)<32: raise RuntimeError("SECRET_KEY must contain at least 32 characters")
    app.config.update(SECRET_KEY=secret,DATABASE_URL=os.getenv("DATABASE_URL",f"sqlite:///{instance/'guard.db'}"),
        ARTIFACT_ROOT=os.getenv("ARTIFACT_ROOT",str(root/"artifacts")),
        SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",SESSION_COOKIE_SECURE=production,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),MAX_CONTENT_LENGTH=2*1024*1024,
        MAX_FORM_MEMORY_SIZE=64*1024,MAX_IMPORT_ROWS=1000,RATE_LIMIT_ENABLED=True,
        TRUSTED_HOSTS=os.getenv("TRUSTED_HOSTS","localhost,127.0.0.1").split(","),
        JSON_SORT_KEYS=False, REDIS_URL=os.getenv("REDIS_URL"),
        TRUSTED_PROXY_CIDRS=os.getenv("TRUSTED_PROXY_CIDRS", "").split(","),
        PROXY_HOPS=int(os.getenv("PROXY_HOPS", "0")), SCORE_RATE_LIMIT=120,
        REVIEW_CAPACITY_PER_DAY=int(os.getenv("REVIEW_CAPACITY_PER_DAY", "100")))
    if config:app.config.update(config)
    if production and not app.config["REDIS_URL"]:
        raise RuntimeError("Production requires REDIS_URL for shared rate limiting")
    hops=app.config["PROXY_HOPS"]
    if not 0<=hops<=10:raise RuntimeError("PROXY_HOPS must be between 0 and 10")
    if hops:
        if not any(app.config["TRUSTED_PROXY_CIDRS"]):
            raise RuntimeError("PROXY_HOPS requires TRUSTED_PROXY_CIDRS")
        app.wsgi_app=TrustedProxy(app.wsgi_app,app.config["TRUSTED_PROXY_CIDRS"],hops)
    app.extensions["rate_limiter"]=Limiter(app.config["REDIS_URL"])
    engine,factory=connect(app.config["DATABASE_URL"])
    app.extensions.update(db_engine=engine,db_factory=factory,model_store=ModelStore(app.config["ARTIFACT_ROOT"]))
    logging.basicConfig(level=logging.INFO,format="%(message)s")

    @app.before_request
    def protect():
        g.started=time.perf_counter();g.request_id=secrets.token_hex(8);g.user=None
        if "csrf" not in session:session["csrf"]=secrets.token_urlsafe(32)
        if request.endpoint in ("static","web.health","web.ready"):return
        if session.get("user_id"):
            with factory() as db:
                user=db.get(User,session["user_id"])
                if user and user.active:g.user=user
                else:
                    session.clear()
                    session["csrf"]=secrets.token_urlsafe(32)
        public={"web.login_page","web.csrf","web.login"}
        if request.endpoint not in public and not g.user:
            if request.path.startswith("/api/"):return jsonify(error="Authentication required"),401
            return redirect(url_for("web.login_page"))
        if request.method in ("POST","PUT","PATCH","DELETE"):
            supplied=request.headers.get("X-CSRF-Token","") or request.form.get("csrf_token","")
            if not supplied or not hmac.compare_digest(supplied,session.get("csrf","")):
                return jsonify(error="Invalid or missing CSRF token; reload the page"),403

    @app.after_request
    def secure(response):
        response.headers.update({"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY",
            "Referrer-Policy":"same-origin","Cache-Control":"no-store",
            "Content-Security-Policy":"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            "X-Request-ID":getattr(g,"request_id","")})
        if production:response.headers["Strict-Transport-Security"]="max-age=31536000"
        app.logger.info(json.dumps({"event":"request","request_id":getattr(g,"request_id",None),
            "method":request.method,"route":str(request.url_rule or "unmatched"),"status":response.status_code,
            "duration_ms":round((time.perf_counter()-getattr(g,"started",time.perf_counter()))*1000,2)}))
        return response

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc,HTTPException):
            return jsonify(error=exc.description),exc.code
        app.logger.error(json.dumps({"event":"request_error","request_id":getattr(g,"request_id",None),"type":type(exc).__name__}))
        return jsonify(error="Unexpected server error",request_id=getattr(g,"request_id",None)),500

    from .routes import web
    app.register_blueprint(web)
    return app


def rate_allowed(bucket,limit,seconds=60):
    from flask import current_app
    if not current_app.config["RATE_LIMIT_ENABLED"]:return True
    return current_app.extensions["rate_limiter"].allowed(bucket,limit,seconds)
