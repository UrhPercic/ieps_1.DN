import time
from threading import Thread
from downloader import download_page
from extractor import extract_links, extract_images
from datastore import DataStore
from duplicate_detector import DuplicateDetector
from frontier import URLFrontier
from utils import get_content_type, download_and_convert_image_to_binary, get_page_type, download_binary_content, hash_html_content

frontier = URLFrontier()
datastore = DataStore()
duplicate_detector = DuplicateDetector(datastore)

seed_urls = ["http://gov.si", "http://evem.gov.si", "http://e-uprava.gov.si", "http://e-prostor.gov.si"]
for url in seed_urls:
    frontier.add_url(url)

num_worker_threads = 4

def get_site_id_from_url(url):
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    return datastore.get_or_create_site_id(domain)

site_ids = {}
for url in seed_urls:
    site_id = get_site_id_from_url(url)
    site_ids[url] = site_id
    frontier.add_url(url)


def crawl():
    while not frontier.empty():
        url = frontier.get_url()

        global site_ids

        site_id = site_ids.get(url, None)
        if site_id is None:
            site_id = get_site_id_from_url(url)
            site_ids[url] = site_id

        content, status_code = download_page(url)

        if content is not None and status_code == 200:

            page_type = get_page_type(url)

            if page_type == 'HTML':
                if duplicate_detector.is_duplicate(content):
                    datastore.store_page(site_id, 'DUPLICATE', url, None, status_code, time.strftime('%d-%m-%Y %H:%M:%S'), None)
                else:
                    link_tuples = extract_links(content, url)
                    images = extract_images(content)
                    html_hash = hash_html_content(content)
                    page_id = datastore.store_page(site_id, 'HTML', url, content, status_code, time.strftime('%d-%m-%Y %H:%M:%S'), html_hash)

                    from_page_id = datastore.get_page_id_by_base_url(url)
                    datastore.store_link(from_page_id, page_id)

                    for image_url in images:
                        content_type = get_content_type(image_url)
                        image_data = download_and_convert_image_to_binary(url, image_url)
                        truncated_image_url = image_url[:255]
                        datastore.store_image(page_id, truncated_image_url, content_type, image_data, time.strftime('%d-%m-%Y %H:%M:%S'))

                    for _, link_url in link_tuples:
                        canonicalized_link_url = duplicate_detector.canonicalize(link_url)
                        frontier.add_url(canonicalized_link_url)
            else:
                binary_data = download_binary_content(url)
                if binary_data:
                    page_id = datastore.store_page(site_id, 'BINARY', url, None, status_code, time.strftime('%d-%m-%Y %H:%M:%S'), None)
                    datastore.store_page_data(page_id, page_type, binary_data)
        else:
            print(f"Failed to fetch content from {url}")
        time.sleep(5)

def start_crawling():
    threads = []
    for i in range(num_worker_threads):
        thread = Thread(target=crawl)
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

if __name__ == '__main__':
    start_crawling()