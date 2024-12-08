import dash
from flask import Flask

# Initialize the Flask server
server = Flask(__name__)

# Initialize the Dash app with the Flask server
app = dash.Dash(__name__, server=server, url_base_pathname='/squad/')

# Import the layout and callbacks from the squad_page module
from squad_page import layout, register_callbacks

# Set the layout of the app
app.layout = layout

# Register callbacks
register_callbacks(app)

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True) 