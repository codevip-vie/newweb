from app import create_app
from models import db_session, Movie, Poster, Founder
from routes.media import movie_cover_url, poster_image_url, founder_image_url

app = create_app()
with app.app_context():
    print('Movies count:', db_session.query(Movie).count())
    print('Posters count:', db_session.query(Poster).count())
    print('Founders count:', db_session.query(Founder).count())
    movie = db_session.query(Movie).first()
    poster = db_session.query(Poster).first()
    founder = db_session.query(Founder).first()
    print('Movie record:', movie.id if movie else None, movie.cover_filename if movie else None)
    print('Movie URL:', movie_cover_url(movie) if movie else None)
    print('Poster record:', poster.id if poster else None, poster.image_filename if poster else None)
    print('Poster URL:', poster_image_url(poster) if poster else None)
    print('Founder record:', founder.id if founder else None, founder.image_filename if founder else None)
    print('Founder URL:', founder_image_url(founder.image_filename) if founder and founder.image_filename else None)
    resp = app.test_client().get('/')
    print('Home status:', resp.status_code)
    html = resp.data.decode('utf-8')
    print('Hero contains image url:', 'https://drive.google.com/uc?export=download&id=' in html)
    print('Home img count:', html.count('img src="https://drive.google.com/uc?export=download&id='))
