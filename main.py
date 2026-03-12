import os
import sys


sys.path.insert(0, os.path.dirname(__file__))


def application(environ, start_response):
    body = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Coming Soon</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    html, body {
      margin: 0;
      padding: 0;
      background: #0f172a;
      color: #e5e7eb;
      font-family: Arial, sans-serif;
      height: 100%;
    }
    .wrap {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 24px;
      box-sizing: border-box;
    }
    .card {
      max-width: 640px;
      background: #111827;
      border: 1px solid #1f2937;
      border-radius: 18px;
      padding: 48px 32px;
      box-shadow: 0 20px 50px rgba(0,0,0,0.35);
    }
    h1 {
      margin: 0 0 12px 0;
      font-size: 42px;
      line-height: 1.1;
    }
    p {
      margin: 0;
      font-size: 18px;
      color: #cbd5e1;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Coming Soon</h1>
      <p>This site will be available soon.</p>
    </div>
  </div>
</body>
</html>
""".encode("utf-8")

    start_response(
        "200 OK",
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]
