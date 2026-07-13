# PROMPTWEB.md

# Professional Movie Website Specification for Codex

## Mission

Build a production-ready Movie Management Website.

### Mandatory Stack

-   HTML5
-   CSS3
-   Vanilla JavaScript
-   Python Flask
-   SQLAlchemy
-   SQLite (easy to replace with MySQL)
-   Flask-Login
-   Werkzeug password hashing

Forbidden: - Node.js - React - Vue - Angular - Bootstrap - Tailwind

## UI Style

Create a premium anti-slop interface inspired by the provided Xiaomi
homepage layout.

Layout: 1. Sticky Header 2. Hero Banner 3. Featured Posters 4. Featured
Movies 5. Author Banner 6. Footer

Use: - glassmorphism - smooth animations - rounded cards - modern
spacing - responsive design - accessibility

## Authentication

Register: - username - email - password - confirm password

Validation: - username unique - email unique - password confirmation -
server-side validation

Login: - username OR email - password

Passwords must be hashed.

## Dashboard

After login display dashboard containing:

-   Home
-   Manage Poster
-   Movie Manager
-   Profile
-   Logout

## Poster Manager

CRUD posters.

Fields: - title - description - image (PNG/JPEG only)

Features: - upload - edit - delete - preview - search

## Movie Manager

CRUD movies.

Fields: - title - description - cover image PNG/JPEG - mp4 video

Maximum video size: 5GB

Features: - upload - progress bar - edit - delete - search - watch movie

## Home

Hero carousel.

Poster advertisement section.

Each poster contains:

-   image
-   title
-   short description
-   View Details button

Movie section:

-   cover
-   title
-   Watch button

Footer:

Display author image and information.

## Security

-   CSRF protection
-   secure upload filenames
-   validate mime types
-   validate extensions
-   authentication required
-   session management

## Folder Structure

app.py config.py models.py routes/ templates/ static/ instance/

## Coding Rules

Implement every feature completely. Never leave TODOs. Produce clean
reusable code. Use Jinja templates. Separate HTML CSS JavaScript.
Responsive on desktop tablet mobile.

Deliver a professional production-ready application.
