from html import unescape
import re
from app import create_app
from models import db_session, Poster, Movie
from routes.media import poster_image_url, movie_cover_url

app = create_app()

with app.app_context():
    p = db_session.query(Poster).first()
    m = db_session.query(Movie).first()

    print('=== DB STORED VALUES ===')
    if p:
        print('poster id:', p.id)
        print('poster.image_filename:', repr(p.image_filename))
        print('poster helper output:', poster_image_url(p))
    else:
        print('poster: NONE')
    if m:
        print('movie id:', m.id)
        print('movie.cover_filename:', repr(m.cover_filename))
        print('movie helper output:', movie_cover_url(m))
    else:
        print('movie: NONE')

    print('\n=== RENDERED HTML SOURCE ===')
    pages = [('/', 'home'), ('/dashboard/movies', 'movies_index'), ('/dashboard/posters', 'posters_index')]
    for path, name in pages:
        resp = app.test_client().get(path)
        html = resp.data.decode('utf-8')
        print('\n---', name, path, 'status', resp.status_code, '---')
        for i, line in enumerate(html.splitlines(), 1):
            if 'src="' in line or 'poster="' in line or 'style="' in line:
                print(f'{i}: {line}')
        print('--- parsed src attributes ---')
        img_srcs = re.findall(r'src="([^"]+)"', html)
        for src in img_srcs:
            print('raw:', repr(src), 'unescaped:', repr(unescape(src)))
        print('--- parsed poster/style urls ---')
        style_urls = re.findall(r'url\(\'([^\']+)\'\)|url\("([^"]+)"\)', html)
        for url in style_urls:
            print('url:', repr(url[0] or url[1]))

    print('\n=== DETAIL PAGE SOURCES ===')
    if p:
        resp = app.test_client().get(f'/posters/{p.id}')
        html = resp.data.decode('utf-8')
        print('poster detail status', resp.status_code)
        for i, line in enumerate(html.splitlines(), 1):
            if 'src="' in line:
                print(f'{i}: {line}')
    if m:
        resp = app.test_client().get(f'/movies/{m.id}/watch')
        html = resp.data.decode('utf-8')
        print('movie watch status', resp.status_code)
        for i, line in enumerate(html.splitlines(), 1):
            if 'src="' in line or 'poster="' in line:
                print(f'{i}: {line}')
