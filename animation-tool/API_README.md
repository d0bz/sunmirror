# Sun Mirror Animation API Documentation

This directory contains a Swagger UI implementation for the Sun Mirror Animation API, allowing you to interactively test and explore the available endpoints.

## Accessing the API Documentation

1. Start the animation server:
   ```
   python server.py
   ```

2. Open your browser and navigate to:
   ```
   http://localhost:80/api
   ```

3. This will redirect you to the API documentation page where you can:
   - View a summary of available endpoints
   - Access the Swagger UI for interactive testing
   - View the raw API specification (swagger.json)

## Available Endpoints

### POST /play_animation
- **Description**: Play an animation on the Sun Mirror
- **Request Body**: JSON containing animation frames and loop parameter
- **Example**:
  ```json
  {
    "frames": [...],
    "loop": false
  }
  ```

### GET /kill_animation
- **Description**: Stop any currently running animation
- **Response**: Status message indicating whether an animation was stopped

### POST /shutdown
- **Description**: Shutdown the animation server
- **Response**: Status message indicating the server is shutting down

## Using Swagger UI

The Swagger UI provides an interactive interface to:
1. Explore API endpoints and their parameters
2. Send test requests directly from the browser
3. View response data in a formatted way

To use it:
1. Navigate to `/swagger-ui.html` or click the "Open Swagger UI" button on the API docs page
2. Expand an endpoint by clicking on it
3. Click "Try it out" to prepare a request
4. Fill in any required parameters
5. Click "Execute" to send the request
6. View the response below

## API Specification

The raw API specification is available at `/swagger.json`. This file follows the OpenAPI 3.0 standard and can be imported into other API tools if needed.
