# _VERCEL_PATH_FIX
import os, sys
from pathlib import Path
_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR))
sys.path.insert(0, str(_DIR.parent))
if (_DIR / 'static').exists() or (_DIR / 'templates').exists():
    os.chdir(_DIR)

from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

reviews = []

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        reviews.append({"title": title, "content": content})
        return redirect(url_for("index"))
    return render_template("index.html", reviews=reviews)

if __name__ == "__main__":
    app.run(debug=True)
