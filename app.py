from datetime import datetime, timedelta
import random
import string

from flask import Flask, request, redirect, render_template
from pony.flask import Pony
from pony.orm import Database, PrimaryKey, Required, Optional, Set, select, commit, db_session
import click
import secrets

import registry

app = Flask(__name__)
app.config.update(dict(
    DEBUG = True,
    SECRET_KEY = "secret_xxx",
    PONY = {
        "provider": "sqlite",
        "filename": "updateasap.db3",
        "create_db": True
    }
))

db = Database()

class User(db.Entity):
    id = PrimaryKey(int, auto=True)
    email = Required(str)
    email_norm = Required(str, unique=True)
    link_secret = Required(str)
    alerts = Set("Alert", reverse="user")

class Alert(db.Entity):
    user = Required(User)
    service = Required(str)
    enabled = Required(bool)
    level = Required(str)
    latest = Optional(str)

class Version(db.Entity):
    service = Required(str, unique=True)
    latest = Required(str)
    last_checked = Optional(datetime)

db.bind(**app.config["PONY"])
db.generate_mapping(create_tables=True)

Pony(app)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/send_manage_link", methods=["POST"])
@db_session
def send_manage_link():
    to = request.form["email"]

    user = User.get(email_norm=to)
    if not user:
        user = User(
            email=to,
            email_norm=to, # TODO: Normalize email address.
            link_secret=secrets.token_urlsafe(32)
        )
    else:
        user.link_secret = secrets.token_urlsafe(32)
        commit()

    email = {
        "to": to,
        "link_secret": user.link_secret
    }

    if app.config["DEBUG"]:
        return "<a href=\"/manage?email=%s&secret=%s\">Manage Alerts</a>" % (user.email_norm, user.link_secret)

    # TODO: Send the email.

    return redirect("/")

@app.route("/manage", methods=["GET"])
@db_session
def manage():
    email = request.args["email"]
    secret = request.args["secret"]

    user = User.get(email_norm=email, link_secret=secret)
    if not user:
        return render_template("error.html", message="This manage link is invalid.", go_home=True)

    alerts = select(a for a in Alert if a.user.id == user.id)

    alert_services = list(map(lambda a: a.service, alerts))
    versions = select(v for v in Version if v.service in alert_services)
    versions_dict = {}
    for version in versions:
        versions_dict[version.service] = version
    alert_services_dict = {}
    for alert in alerts:
        alert_services_dict[alert.service] = True

    return render_template(
        "manage.html",
        user=user,
        Services=registry.Services,
        versions_dict=versions_dict,
        alerts=alerts,
        alert_services_dict=alert_services_dict,
    )

@app.route("/manage/add_alert", methods=["POST"])
@db_session
def manage_add_alert():
    email = request.args["email"]
    secret = request.args["secret"]

    user = User.get(email_norm=email, link_secret=secret)
    if not user:
        return render_template("error.html", message="This manage link is invalid.", go_home=True)

    Alert(
        user=user,
        service=request.form["serviceId"],
        enabled=True,
        level="Major",
    )

    return redirect("/manage?email=%s&secret=%s" % (email, secret))

@app.route("/manage/delete_alert", methods=["POST"])
@db_session
def manage_delete_alert():
    email = request.args["email"]
    secret = request.args["secret"]

    user = User.get(email_norm=email, link_secret=secret)
    if not user:
        return render_template("error.html", message="This manage link is invalid.", go_home=True)

    alert = Alert.get(
        user=user,
        service=request.form["serviceId"],
    )
    if alert:
        alert.delete()

    return redirect("/manage?email=%s&secret=%s" % (email, secret))

@app.route("/manage/update_alert_level", methods=["POST"])
@db_session
def manage_update_alert_level():
    email = request.args["email"]
    secret = request.args["secret"]

    user = User.get(email_norm=email, link_secret=secret)
    if not user:
        return render_template("error.html", message="This manage link is invalid.", go_home=True)

    alert = Alert.get(
        user=user,
        service=request.form["serviceId"],
    )
    if not alert:
        return "No such alert exists."

    alert.level = request.form["level"]
    commit()

    return redirect("/manage?email=%s&secret=%s" % (email, secret))

@app.cli.command("check-updates")
@click.option("-f", "--force", is_flag=True)
@db_session
def check_updates(force):
    for k, Service in registry.Services.items():
        now = datetime.now()
        version = Version.get(service=k)
        if not force and (version.last_checked-now) / timedelta(hours=1) < 1:
            print("%s: Last checked %s. Fresh. Skipping." % (Service.name, version.last_checked))
            continue
        last_version = None
        latest = Service.latest()
        if not version:
            version = Version(
                service=k,
                latest=str(latest),
                last_checked=datetime.now(),
            )
        else:
            last_version = version.latest
            version.latest = str(latest)
            version.last_checked = now
            commit()
        if Service.versioning.compare(last_version, latest) == -1:
            print("%s: Last: %s. Latest: %s." % (Service.name, last_version, latest))
        else:
            print("%s: Last %s. No Updates." % (Service.name, last_version))
