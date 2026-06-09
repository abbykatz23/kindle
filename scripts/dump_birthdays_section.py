from web.app import create_app

app = create_app()
with app.test_client() as c:
    r = c.get('/')
    html = r.data.decode('utf-8')
    start = html.find('id="birthdays"')
    if start == -1:
        print('NO_BIRTHDAYS_SECTION')
    else:
        snippet = html[start:start+1200]
        with open('tmp_birthdays_section.html','w', encoding='utf-8') as f:
            f.write(snippet)
        print('WROTE tmp_birthdays_section.html')
