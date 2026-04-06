from app import create_app

# Expose at module level — used by Passenger (passenger_wsgi.py) and WSGI servers
app = create_app()

# Entry point for local development only.
# Never set debug=True here; the value comes from the environment and
# create_app() always sets DEBUG=False for safety.
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
