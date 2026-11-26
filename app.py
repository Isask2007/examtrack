"""ExamTrack application entry point.

Run with:
    flask --app app run --debug
or:
    python app.py
"""

from exatrms import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
