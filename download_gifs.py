import urllib.request
import re
import os

os.makedirs("gifs", exist_ok=True)

def download_gifs(query, category):
    req = urllib.request.Request(f"https://tenor.com/search/{query}-gifs", headers={'User-Agent': 'Mozilla/5.0'})
    try:
        html = urllib.request.urlopen(req).read().decode('utf-8')
        gifs = list(set(re.findall(r'https://media1\.tenor\.com/m/[a-zA-Z0-9_-]+/[^"]+\.gif', html)))
        if not gifs:
            gifs = list(set(re.findall(r'https://media\.tenor\.com/[^"]+\.gif', html)))
        
        for i, gif in enumerate(gifs[:3]):
            print(f"Downloading {gif} for {category}")
            urllib.request.urlretrieve(gif, f"gifs/{category}_{i}.gif")
    except Exception as e:
        print(f"Failed {category}: {e}")

download_gifs("anime-angry", "angry")
download_gifs("anime-blush", "blush")
download_gifs("anime-pout", "hmph")
