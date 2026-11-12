from flask import Flask, jsonify

app = Flask(__name__)


@app.get("/")
def index():
    return jsonify({"status": "ok", "message": "Ledger API is running"})


if __name__ == "__main__":
    app.run(debug=True)
