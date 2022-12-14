from datetime import datetime, timedelta
import random
import string

from flask import Flask, request, redirect, render_template
from flask_mail import Mail, Message
from pony.flask import Pony
from pony.orm import Database, PrimaryKey, Required, Optional, Set, StrArray, select, commit, db_session
from slack_sdk.webhook import WebhookClient
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

mail = Mail(app)

db = Database()

class User(db.Entity):
    id = PrimaryKey(int, auto=True)
    email = Required(str)
    email_norm = Required(str, unique=True)
    link_secret = Required(str)
    slack_webhook_url = Optional(str)
    alerts = Set("Alert", reverse="user")
    email_notification = Optional("EmailNotification")
    slack_notification = Optional("SlackNotification")

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
    hot = Required(bool)

class EmailNotification(db.Entity):
    user = Required(User, unique=True)
    services = Required(StrArray)
    failed = Required(int)

class SlackNotification(db.Entity):
    user = Required(User, unique=True)
    services = Required(StrArray)
    failed = Required(int)

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
        if not force and version != None and (version.last_checked-now) / timedelta(hours=1) < 1:
            print("%s: Last checked %s. Fresh. Skipping." % (Service.name, version.last_checked))
            continue
        last_version = None
        latest = Service.latest()
        if not version:
            version = Version(
                service=k,
                latest=str(latest),
                last_checked=datetime.now(),
                hot=False,
            )
            print("%s: Latest: %s." % (Service.name, latest))
        else:
            last_version = version.latest
            version.latest = str(latest)
            version.last_checked = now
            version.hot = True
            commit()
            if Service.versioning.compare(last_version, latest) == -1:
                print("%s: Last: %s. Latest: %s." % (Service.name, last_version, latest))
            else:
                print("%s: Last %s. No Updates." % (Service.name, last_version))

@app.cli.command("make-notifications")
@db_session
def make_notifications():
    for k, Service in registry.Services.items():
        version = Version.get(service=k)
        if not version or not version.hot:
            continue
        services = []
        for user in select(u for u in User):
            alert = Alert.get(user=user, service=k)
            if not alert:
                continue
            services.append(version.service)
            Notifs = [EmailNotification]
            if user.slack_webhook_url:
                Notifs.append(SlackNotification)
            for Notif in Notifs:
                notif = Notif.get(user=user)
                if not notif:
                    Notif(
                        user=user,
                        services=services,
                        failed=0,
                    )
                else:
                    if k not in notif.services:
                        notif.services.append(k)
        version.hot = False
        commit()

@app.cli.command("send-email-notifications")
@db_session
def send_email_notifications():
    for notif in select(n for n in EmailNotification):
        updates = []
        for k, Service in registry.Services.items():
            version = Version.get(service=k)
            if not version:
                continue
            if k in notif.services:
                updates.append("%s (%s)" % (Service.name, version.latest))
        subject = ""
        body = ""
        if len(updates) == 1:
            subject = "[UpdateASAP] A new version is now available."
            body = "A new version of %s is out." % (
                ", ".join(updates)
            )
        else:
            subject = "[UpdateASAP] New versions are now available."
            body = "New versions of %s and %s are out." % (
                ", ".join(updates[:-1]),
                updates[-1],
            )
        msg = Message(subject, sender="alerts@updateasap.fsapp.co", recipients=[notif.user.email])
        msg.body = body
        print(msg)
        try:
            mail.send(msg)
        except:
            if notif.failed < 3:
                notif.failed += 1
                commit()
            else:
                notif.delete()

@app.cli.command("send-slack-notifications")
@db_session
def send_slack_notifications():
    for notif in select(n for n in SlackNotification):
        url = notif.user.slack_webhook_url
        if not url:
            notif.delete()
            continue
        updates = []
        for k, Service in registry.Services.items():
            version = Version.get(service=k)
            if not version:
                continue
            if k in notif.services:
                updates.append("%s (%s)" % (Service.name, version.latest))
        text = ""
        if len(updates) == 1:
            text = "A new version of %s is out." % (
                ", ".join(updates)
            )
        else:
            text = "New versions of %s and %s are out." % (
                ", ".join(updates[:-1]),
                updates[-1],
            )
        client = WebhookClient(url)
        resp = client.send(text=text)
        if not resp.status_code == 200:
            if notif.failed < 3:
                notif.failed += 1
                commit()
            else:
                notif.delete()
