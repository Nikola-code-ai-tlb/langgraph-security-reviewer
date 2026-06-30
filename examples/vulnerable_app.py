"""A deliberately insecure sample app — input for the reviewer.

Every function below contains at least one planted vulnerability spanning the
categories the orchestrator knows about. Use it to watch the agent work:

    python run_review.py examples/vulnerable_app.py

DO NOT deploy this. It exists only to be torn apart by the review agent.
"""

import hashlib
import os
import pickle
import sqlite3
import subprocess

import yaml
from flask import Flask, request

app = Flask(__name__)

# secrets: hardcoded credentials committed to source control.
DB_PASSWORD = "hunter2-super-secret"
API_TOKEN = "sk-live-9f8a7b6c5d4e3f2a1b0c"


def get_user(username):
    # injection: SQL built with string formatting — classic SQL injection.
    conn = sqlite3.connect("app.db")
    query = "SELECT * FROM users WHERE name = '%s'" % username
    return conn.execute(query).fetchall()


def hash_password(password):
    # cryptography: MD5 is broken for password hashing (fast, unsalted).
    return hashlib.md5(password.encode()).hexdigest()


def load_profile(serialized):
    # deserialization: pickle.loads on untrusted input is remote code execution.
    return pickle.loads(serialized)


def load_config(raw):
    # deserialization: yaml.load without SafeLoader can instantiate objects.
    return yaml.load(raw)


def run_backup(filename):
    # injection: shell=True with user input -> command injection.
    subprocess.call("tar -czf backup.tar.gz " + filename, shell=True)


def read_file(path):
    # input_validation: no path sanitization -> path traversal (../../etc/passwd).
    with open(os.path.join("/var/data", path)) as fh:
        return fh.read()


@app.route("/run")
def run_handler():
    # injection: eval on a request parameter -> arbitrary code execution.
    expr = request.args.get("expr")
    return str(eval(expr))


if __name__ == "__main__":
    # misconfiguration: debug=True exposes the Werkzeug debugger (RCE) in prod.
    app.run(host="0.0.0.0", debug=True)
