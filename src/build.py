import os
import shutil
import re
import jinja2
import markdown
import requests
import zipfile
import pybtex.database
import json
import sys
from config import *
from ext import get_ext


def build():
    md = markdown.Markdown(extensions=EXT)
    print("Detecting if contents present...")
    do_clone = detect_if_contents_present(IMPORT_FILES)
    if do_clone:
        print("No contents present, cloning...")
        clone_contents(CONTENTS_ZIP, AAA_ORIGIN)
        print("Cloned, extracting...")
        extract_contents(CONTENTS_ZIP, AAA_REPO_PATH, TMP_OUTPUT_DIRECTORY, OUTPUT_DIRECTORY)
        print("Extracted, moving files...")
        move_from_contents(OUTPUT_DIRECTORY, IMPORT_FILES)
        print("Cleaning up...")
        clean_up(CONTENTS_ZIP, TMP_OUTPUT_DIRECTORY, OUTPUT_DIRECTORY)
    else:
        print("Contents already exists.")

    try:
        print("Trying to create _book directory...")
        os.mkdir(O_NAME)
        print("Successfully created.")
    except FileExistsError:
        print("_book already exists. Removing...")
        shutil.rmtree(O_NAME)
        print("Making _book...")
        os.mkdir(O_NAME)

    print("Making contents folder...")
    os.mkdir(f"{O_NAME}/{CONTENTS_NAME}")

    print("Done making, looking for chapters...")
    chapters = filter(lambda a: re.match('^[a-zA-Z0-9_-]+$', a), os.listdir(CONTENTS_NAME))

    print("Looking for the template...")
    with open(TEMPLATE_PATH, 'r') as template_file:
        print("Reading...")
        template = jinja2.Template(template_file.read())
        print("Template ready!")

    print("Building Pygments...")
    os.system(f"pygmentize -S {PYGMENT_THEME} -f html -a .codehilite > {O_NAME}/pygments.css")

    print("Parsing SUMMARY.md...")
    summary = parse_summary()

    print("Opening bibtex...")
    bib_database = pybtex.database.parse_file("literature.bib")

    print("Opening book.json...")
    with open("book.json") as bjs:
        book_json = json.load(bjs)

    print("Creating rendering pipeline...")
    renderer = get_ext(bib_database, PYGMENT_THEME, md)

    print("Rendering chapters...")
    for chapter in chapters:
        render_chapter(chapter, renderer, template, summary, book_json)

    print("Moving favicon.ico...")
    shutil.copy(FAVICON_PATH, f"{O_NAME}/favicon.ico")

    print("Moving styles...")
    shutil.copytree(STYLE_PATH, f"{O_NAME}/styles")

    print("Parsing redirects...")
    with open("redirects.json") as rjs_file:
        rjs = json.load(rjs_file)
    rjs = {i["from"]: i["to"] for i in rjs["redirects"]}
    with open(f"{O_NAME}/redirects.json", 'w') as rjs_file:
        json.dump(rjs, rjs_file)

    print("Rendering index...")
    with open(INDEX_NAME, 'r') as readme:
        with open(f"{O_NAME}/index.html", 'w') as index:
            index.write(render_one(readme, f"{O_NAME}/", 0, renderer, template, summary, book_json))
    print("Done!")


def parse_summary():
    with open(SUMMARY_NAME) as s:
        summary = s.read()
    summary = summary.replace(".md", ".html") \
        .replace("(contents", "(/contents") \
        .replace('* ', '') \
        .replace('README', '/index')
    summary_parsed = []
    for index, line in enumerate(summary.split('\n')[2:-1]):
        indent, rest = line.split('[')
        name, link = rest.split('](')
        link = link[:-1]
        current_indent = len(indent) // SUMMARY_INDENT_LEVEL
        summary_parsed.append((name, link, current_indent))
    return summary_parsed


def clean_up(*files):
    for file in files:
        if os.path.isdir(file):
            shutil.rmtree(file)
        else:
            os.remove(file)


def detect_if_contents_present(import_files):
    do_clone = False
    for file in import_files:
        if file not in os.listdir("."):
            do_clone = True
    return do_clone


def clone_contents(contents_zip, origin, disable_stdout_progress=False):
    with open(contents_zip, "wb") as f:
        response = requests.get(origin, stream=True)
        total_length = response.headers.get('content-length')
        if disable_stdout_progress or total_length is None:
            f.write(response.content)
        else:
            dl = 0
            total_length = int(total_length)
            for data in response.iter_content(chunk_size=4096):
                dl += len(data)
                f.write(data)
                done = int(50 * dl / total_length)
                sys.stdout.write("\r[%s%s]" % ('=' * done, ' ' * (50 - done)))
                sys.stdout.flush()


def extract_contents(contents_zip, repo_path, tmp_output_directory, output_directory):
    with zipfile.ZipFile(contents_zip, 'r') as origin_zip:
        origin_zip.extractall(tmp_output_directory)
    shutil.move(f"{tmp_output_directory}/{repo_path}", output_directory)


def move_from_contents(repo_directory, import_files):
    for file, name in import_files.items():
        shutil.move(os.path.join(repo_directory, file), name)


def render_chapter(chapter, renderer, template, summary, book_json):
    os.mkdir(f"{O_NAME}/{CONTENTS_NAME}/{chapter}")
    try:
        md_file: str = next(filter(lambda a: a.endswith(".md"), os.listdir(f"{CONTENTS_NAME}/{chapter}")))
    except StopIteration:
        return
    out_file = f"{O_NAME}/{CONTENTS_NAME}/{chapter}/{md_file.replace('.md', '.html')}"
    with open(f"{CONTENTS_NAME}/{chapter}/{md_file}", 'r') as r:
        try:
            index = [k[0] for k in filter(lambda x: out_file.split('/')[-1] in x[1],
                                          [(i, a[1]) for i, a in enumerate(summary)])][0]
        except IndexError:
            return
        contents: str = render_one(r, f"{CONTENTS_NAME}/{chapter}", index, renderer, template, summary, book_json)
    with open(out_file, 'w') as f:
        f.write(contents)
    try:
        shutil.copytree(f"{CONTENTS_NAME}/{chapter}/res", f"{O_NAME}/{CONTENTS_NAME}/{chapter}/res")
    except FileNotFoundError:
        pass
    try:
        shutil.copytree(f"{CONTENTS_NAME}/{chapter}/code", f"{O_NAME}/{CONTENTS_NAME}/{chapter}/code")
    except FileNotFoundError:
        pass


def render_one(file_handle, code_dir, index, renderer, template, summary, book_json) -> str:
    text = file_handle.read()
    finalized = renderer(text, code_dir)
    rendered = template.render(md_text=finalized, summary=summary, index=index, enumerate=enumerate,
                               bjs=json.dumps(book_json))
    return rendered
