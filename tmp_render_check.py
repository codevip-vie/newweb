from app import create_app
from models import db_session, Movie, Poster
from routes.media import movie_cover_url, poster_image_url

app = create_app()
with app.app_context():
    m = db_session.query(Movie).first()
    p = db_session.query(Poster).first()
    print('movie:', m.id if m else None, m.cover_filename if m else None)
    print('movie_cover_url:', movie_cover_url(m) if m else None)
    print('poster:', p.id if p else None, p.image_filename if p else None)
    print('poster_image_url:', poster_image_url(p) if p else None)
    resp = app.test_client().get('/')
    print('home status:', resp.status_code)
    html = resp.data.decode('utf-8')
    print('home contains movie_cover_url:', 'movie_cover_url' in html)
    print('home sample hero:', html[html.find('hero-slide'):html.find('hero-slide')+250])
    print('home img srcs:', [line for line in html.splitlines() if 'img src=' in line][:10])
