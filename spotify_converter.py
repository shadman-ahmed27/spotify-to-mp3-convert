import os
import re
import tkinter as tk
from tkinter import messagebox, ttk
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
import yt_dlp

# ======= Spotify API Configuration =======
SPOTIFY_CLIENT_ID = "" # Add your own client ID and secret here
SPOTIFY_CLIENT_SECRET = ""  # Add your own client ID and secret here
SPOTIFY_REDIRECT_URI = "http://localhost:8888/callback"  # for user auth (liked songs)
SCOPE = "user-library-read playlist-read-private"

# Create a Spotify client for general searches (Client Credentials flow)
try:
    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        )
    )
except Exception as e:
    print(f"Error setting up Spotify client: {e}")
    exit(1)

# For user authentication (to get liked songs and private playlists)
sp_user = None

# ======= Global Variables for Pagination (Search Tab) =======
search_limit = 10
search_query = ""
search_tracks_offset = 0
search_tracks_total = 0
search_playlists_offset = 0
search_playlists_total = 0

# ======= Global Variables for Pagination (Account Tab) =======
account_limit = 10
account_id = ""
account_playlists_offset = 0
account_playlists_total = 0
account_liked_offset = 0
account_liked_total = 0

# NEW: Global variables for playlist lookup mode
playlist_lookup_mode = False
lookup_playlist_id = ""
lookup_playlist_name = ""

# ======= Helper Functions =======

def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', '_', name)

def parse_spotify_id_from_url(url_or_uri: str, expected_type: str) -> str:
    url_or_uri = url_or_uri.strip()
    if url_or_uri.startswith("spotify:") and expected_type in url_or_uri:
        parts = url_or_uri.split(":")
        if len(parts) == 3:
            return parts[2]
    if "open.spotify.com" in url_or_uri and expected_type in url_or_uri:
        parts = url_or_uri.split("/")
        for i, part in enumerate(parts):
            if part == expected_type and i + 1 < len(parts):
                raw_id = parts[i + 1]
                return raw_id.split("?")[0]
    return url_or_uri

# ======= Download (Conversion) Functions =======

def download_track(track_name, artist_name, target_folder=None):
    status_var.set(f"Downloading: {track_name} - {artist_name}")
    desktop_folder = os.path.join(os.path.expanduser("~"), "Desktop", "SpotifyMP3s")
    if target_folder is None:
        target_folder = os.path.join(desktop_folder, "SpotifySingles")
    os.makedirs(target_folder, exist_ok=True)
    current_dir = os.getcwd()
    os.chdir(target_folder)
    search_query_yt = f"{track_name} {artist_name} audio"
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f"{track_name} - {artist_name}.%(ext)s",
        'noplaylist': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch:{search_query_yt}"])
    except Exception as e:
        status_var.set(f"Error downloading {track_name}: {e}")
    else:
        status_var.set(f"Downloaded: {track_name} - {artist_name}")
    os.chdir(current_dir)

def download_playlist(playlist_id, playlist_name, from_sp_obj=None):
    status_var.set(f"Fetching tracks for playlist: {playlist_name}")
    sanitized_name = sanitize_filename(playlist_name)
    desktop_folder = os.path.join(os.path.expanduser("~"), "Desktop", "SpotifyMP3s")
    playlist_folder = os.path.join(desktop_folder, sanitized_name)
    os.makedirs(playlist_folder, exist_ok=True)
    current_dir = os.getcwd()
    os.chdir(playlist_folder)
    spotify_obj = from_sp_obj if from_sp_obj else sp
    all_tracks = []
    try:
        results = spotify_obj.playlist_items(playlist_id, limit=100)
        all_tracks.extend(results.get("items", []))
        while results.get("next"):
            results = spotify_obj.next(results)
            all_tracks.extend(results.get("items", []))
    except Exception as e:
        messagebox.showerror("Error", f"Could not fetch playlist tracks: {e}")
        os.chdir(current_dir)
        return
    for item in all_tracks:
        track = item.get("track")
        if not track:
            continue
        track_name = track.get("name", "")
        artists = ", ".join([artist["name"] for artist in track.get("artists", [])])
        download_track(track_name, artists, target_folder=playlist_folder)
    status_var.set("Download completed!")
    os.chdir(current_dir)

def show_playlist_tracks_by_id(playlist_id, playlist_name):
    try:
        all_tracks = []
        results = sp.playlist_items(playlist_id, limit=100)
        all_tracks.extend(results.get("items", []))
        while results.get("next"):
            results = sp.next(results)
            all_tracks.extend(results.get("items", []))
    except Exception as e:
        messagebox.showerror("Error", f"Could not fetch playlist tracks: {e}")
        return
    top = tk.Toplevel(root)
    top.title(f"Tracks in {playlist_name}")
    listbox = tk.Listbox(top, width=80)
    listbox.pack(fill=tk.BOTH, expand=True)
    for item in all_tracks:
        track = item.get("track")
        if track:
            tname = track.get("name", "")
            artists = ", ".join([a["name"] for a in track.get("artists", [])])
            listbox.insert(tk.END, f"{tname} - {artists}")

# ======= SEARCH TAB Functions =======

def is_direct_url_or_uri(query: str) -> bool:
    query = query.lower()
    return "spotify.com" in query or query.startswith("spotify:")

def perform_search():
    global search_query, search_tracks_offset, search_playlists_offset
    q = search_entry.get().strip()
    if not q:
        messagebox.showwarning("Input Error", "Please enter a search term, URL, or URI.")
        return
    search_tracks_offset = 0
    search_playlists_offset = 0
    search_query = q
    if is_direct_url_or_uri(q):
        track_id = parse_spotify_id_from_url(q, "track")
        if track_id != q:
            load_direct_track(track_id)
            search_playlists_listbox.delete(0, tk.END)
            return
        playlist_id = parse_spotify_id_from_url(q, "playlist")
        if playlist_id != q:
            load_direct_playlist(playlist_id)
            search_tracks_listbox.delete(0, tk.END)
            return
        artist_id = parse_spotify_id_from_url(q, "artist")
        if artist_id != q:
            load_direct_artist(artist_id)
            return
    load_search_tracks()
    load_search_playlists()

def load_direct_track(track_id):
    global search_tracks_total
    try:
        track = sp.track(track_id)
    except Exception as e:
        messagebox.showerror("Spotify Error", f"Error loading track: {e}")
        return
    search_tracks_listbox.delete(0, tk.END)
    name = track.get("name", "")
    artists = ", ".join([a["name"] for a in track.get("artists", [])])
    search_tracks_listbox.insert(tk.END, f"{name} - {artists}")
    search_playlists_listbox.delete(0, tk.END)
    search_tracks_total = 1

def load_direct_playlist(playlist_id):
    global search_playlists_total
    try:
        playlist = sp.playlist(playlist_id, fields="name")
    except Exception as e:
        messagebox.showerror("Spotify Error", f"Error loading playlist: {e}")
        return
    search_playlists_listbox.delete(0, tk.END)
    name = playlist.get("name", "")
    search_playlists_listbox.insert(tk.END, name)
    search_tracks_listbox.delete(0, tk.END)
    search_playlists_total = 1

def load_direct_artist(artist_id):
    global search_tracks_total
    try:
        artist = sp.artist(artist_id)
    except Exception as e:
        messagebox.showerror("Spotify Error", f"Error loading artist: {e}")
        return
    search_tracks_listbox.delete(0, tk.END)
    search_tracks_listbox.insert(tk.END, f"Artist: {artist.get('name', '')}")
    search_playlists_listbox.delete(0, tk.END)
    search_tracks_total = 1

def load_search_tracks():
    global search_tracks_total
    try:
        result = sp.search(q=search_query, type="track", limit=search_limit, offset=search_tracks_offset)
    except Exception as e:
        messagebox.showerror("Spotify Error", f"Error during track search: {e}")
        return
    tracks = result.get("tracks", {})
    search_tracks_total = tracks.get("total", 0)
    search_tracks_listbox.delete(0, tk.END)
    for item in tracks.get("items", []):
        name = item.get("name", "")
        artists = ", ".join([artist["name"] for artist in item.get("artists", [])])
        search_tracks_listbox.insert(tk.END, f"{name} - {artists}")

def load_search_playlists():
    global search_playlists_total
    try:
        result = sp.search(q=search_query, type="playlist", limit=search_limit, offset=search_playlists_offset)
    except Exception as e:
        messagebox.showerror("Spotify Error", f"Error during playlist search: {e}")
        return
    playlists = result.get("playlists", {})
    search_playlists_total = playlists.get("total", 0)
    search_playlists_listbox.delete(0, tk.END)
    for item in playlists.get("items", []):
        search_playlists_listbox.insert(tk.END, item.get("name", ""))

def search_tracks_next():
    global search_tracks_offset
    if search_tracks_offset + search_limit < search_tracks_total:
        search_tracks_offset += search_limit
        load_search_tracks()

def search_tracks_prev():
    global search_tracks_offset
    if search_tracks_offset - search_limit >= 0:
        search_tracks_offset -= search_limit
        load_search_tracks()

def search_playlists_next():
    global search_playlists_offset
    if search_playlists_offset + search_limit < search_playlists_total:
        search_playlists_offset += search_limit
        load_search_playlists()

def search_playlists_prev():
    global search_playlists_offset
    if search_playlists_offset - search_limit >= 0:
        search_playlists_offset -= search_limit
        load_search_playlists()

def convert_search_selection():
    t_index = search_tracks_listbox.curselection()
    if t_index:
        selected = search_tracks_listbox.get(t_index)
        if " - " in selected:
            track_name, artist_names = selected.split(" - ", 1)
            download_track(track_name, artist_names)
        return
    p_index = search_playlists_listbox.curselection()
    if p_index:
        try:
            if search_playlists_total == 1 and is_direct_url_or_uri(search_query):
                playlist_id = parse_spotify_id_from_url(search_query, "playlist")
                playlist = sp.playlist(playlist_id, fields="name")
                download_playlist(playlist_id, playlist.get("name", ""))
            else:
                result = sp.search(q=search_query, type="playlist", limit=search_limit, offset=search_playlists_offset)
                playlists = result.get("playlists", {}).get("items", [])
                playlist = playlists[p_index[0]]
                playlist_id = playlist.get("id")
                playlist_name = playlist.get("name", "")
                if sp_user is not None and account_id == sp_user.me().get("id"):
                    download_playlist(playlist_id, playlist_name, from_sp_obj=sp_user)
                else:
                    download_playlist(playlist_id, playlist_name)
        except Exception as e:
            messagebox.showerror("Error", f"Could not convert playlist: {e}")
        return
    messagebox.showwarning("No Selection", "Please select a track or playlist to convert.")

# ======= ACCOUNT TAB Functions =======

def parse_user_id(url_or_id: str) -> str:
    url_or_id = url_or_id.strip()
    if "open.spotify.com/user/" in url_or_id:
        parts = url_or_id.split("/user/")
        user_part = parts[-1]
        return user_part.split("?")[0]
    return url_or_id

def user_login():
    global sp_user
    try:
        sp_user = spotipy.Spotify(
            auth_manager=SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope=SCOPE
            )
        )
        user = sp_user.me()
        login_status_var.set(f"Logged in as: {user.get('display_name', user.get('id'))}")
    except Exception as e:
        messagebox.showerror("Login Error", f"Could not log in: {e}")

def load_account_data():
    """
    If the entered value contains 'playlist', treat it as a playlist URL/URI and load that playlist.
    Otherwise, treat it as an account ID/URL and load the account's public playlists and liked songs.
    """
    global account_id, account_playlists_offset, account_liked_offset
    global playlist_lookup_mode, lookup_playlist_id, lookup_playlist_name
    raw_id = account_entry.get().strip()
    if not raw_id:
        messagebox.showwarning("Input Error", "Please enter a user ID, URL, or playlist URL.")
        return
    if "playlist" in raw_id.lower():
        # NEW: Handle playlist lookup mode.
        playlist_lookup_mode = True
        lookup_playlist_id = parse_spotify_id_from_url(raw_id, "playlist")
        try:
            playlist = sp.playlist(lookup_playlist_id, fields="name")
            lookup_playlist_name = playlist.get("name", "")
        except Exception as e:
            messagebox.showerror("Error", f"Could not load playlist: {e}")
            return
        account_playlists_listbox.delete(0, tk.END)
        account_playlists_listbox.insert(tk.END, lookup_playlist_name)
        # Bind double-click to show its tracks.
        account_playlists_listbox.bind("<Double-Button-1>", lambda event: show_playlist_tracks_by_id(lookup_playlist_id, lookup_playlist_name))
        status_var.set(f"Loaded playlist: {lookup_playlist_name}")
        # Clear account_id so that later account functions don't run.
        account_id = ""
        return

    # Otherwise, treat the input as an account lookup.
    playlist_lookup_mode = False
    account_id = parse_user_id(raw_id)
    account_playlists_offset = 0
    account_liked_offset = 0
    load_account_playlists()
    load_account_liked_songs()

def load_account_playlists():
    global account_playlists_total
    account_playlists_listbox.delete(0, tk.END)
    try:
        result = sp.user_playlists(account_id, limit=account_limit, offset=account_playlists_offset)
    except Exception as e:
        messagebox.showerror("Error", f"Could not load playlists: {e}")
        return
    account_playlists_total = result.get("total", 0)
    for item in result.get("items", []):
        account_playlists_listbox.insert(tk.END, item.get("name", ""))

def load_account_liked_songs():
    global account_liked_total
    account_liked_listbox.delete(0, tk.END)
    if sp_user is None:
        account_liked_listbox.insert(tk.END, "Please log in to load liked songs.")
        account_liked_total = 0
        return
    current_user = sp_user.me().get("id")
    if account_id != current_user:
        account_liked_listbox.insert(tk.END, "Liked songs only available for the logged-in account.")
        account_liked_total = 0
        return
    try:
        result = sp_user.current_user_saved_tracks(limit=account_limit, offset=account_liked_offset)
    except Exception as e:
        messagebox.showerror("Error", f"Could not load liked songs: {e}")
        return
    account_liked_total = result.get("total", 0)
    for item in result.get("items", []):
        track = item.get("track")
        if track:
            track_name = track.get("name", "")
            artists = ", ".join([a["name"] for a in track.get("artists", [])])
            account_liked_listbox.insert(tk.END, f"{track_name} - {artists}")

def account_playlists_next():
    global account_playlists_offset
    if account_playlists_offset + account_limit < account_playlists_total:
        account_playlists_offset += account_limit
        load_account_playlists()

def account_playlists_prev():
    global account_playlists_offset
    if account_playlists_offset - account_limit >= 0:
        account_playlists_offset -= account_limit
        load_account_playlists()

def account_liked_next():
    global account_liked_offset
    if account_liked_offset + account_limit < account_liked_total:
        account_liked_offset += account_limit
        load_account_liked_songs()

def account_liked_prev():
    global account_liked_offset
    if account_liked_offset - account_limit >= 0:
        account_liked_offset -= account_limit
        load_account_liked_songs()

def convert_account_selection():
    # NEW: If we are in playlist lookup mode, directly convert that playlist.
    if playlist_lookup_mode:
        if lookup_playlist_id:
            try:
                download_playlist(lookup_playlist_id, lookup_playlist_name)
            except Exception as e:
                messagebox.showerror("Error", f"Could not convert playlist: {e}")
            return

    p_index = account_playlists_listbox.curselection()
    if p_index:
        try:
            result = sp.user_playlists(account_id, limit=account_limit, offset=account_playlists_offset)
            playlists = result.get("items", [])
            playlist = playlists[p_index[0]]
            playlist_id = playlist.get("id")
            playlist_name = playlist.get("name", "")
            if sp_user is not None and account_id == sp_user.me().get("id"):
                download_playlist(playlist_id, playlist_name, from_sp_obj=sp_user)
            else:
                download_playlist(playlist_id, playlist_name)
        except Exception as e:
            messagebox.showerror("Error", f"Could not convert playlist: {e}")
        return
    l_index = account_liked_listbox.curselection()
    if l_index:
        if sp_user is None:
            messagebox.showwarning("Not Logged In", "You must log in to download liked songs.")
            return
        try:
            result = sp_user.current_user_saved_tracks(limit=account_limit, offset=account_liked_offset)
            items = result.get("items", [])
            item = items[l_index[0]]
            track = item.get("track")
            if track:
                track_name = track.get("name", "")
                artists = ", ".join([a["name"] for a in track.get("artists", [])])
                download_track(track_name, artists)
        except Exception as e:
            messagebox.showerror("Error", f"Could not convert track: {e}")
        return
    messagebox.showwarning("No Selection", "Please select a playlist or liked song to convert.")

# ======= GUI Setup =======
root = tk.Tk()
root.title("Spotify Converter")
root.geometry("1000x700")
root.resizable(True, True)
root.option_add("*Font", ("Segoe UI", 10))

style = ttk.Style(root)
style.theme_use("clam")

notebook = ttk.Notebook(root)
notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

status_var = tk.StringVar(value="Status: Ready")
login_status_var = tk.StringVar(value="Not logged in")

# ----- TAB 1: SEARCH -----
search_tab = ttk.Frame(notebook)
notebook.add(search_tab, text="Search")
search_frame = ttk.Frame(search_tab, padding="10")
search_frame.pack(fill=tk.X)
search_label = ttk.Label(search_frame, text="Search Query / URL / URI:", font=("Segoe UI", 11))
search_label.pack(side=tk.LEFT)
search_entry = ttk.Entry(search_frame, width=50)
search_entry.pack(side=tk.LEFT, padx=10)
search_button = ttk.Button(search_frame, text="Search", command=perform_search)
search_button.pack(side=tk.LEFT)
search_entry.bind("<Return>", lambda e: perform_search())

results_frame = ttk.Frame(search_tab, padding="10")
results_frame.pack(fill=tk.BOTH, expand=True)
tracks_frame = ttk.Labelframe(results_frame, text="Tracks")
tracks_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,5))
search_tracks_listbox = tk.Listbox(tracks_frame)
search_tracks_listbox.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
tracks_scroll = ttk.Scrollbar(tracks_frame, command=search_tracks_listbox.yview)
tracks_scroll.pack(side=tk.RIGHT, fill=tk.Y)
search_tracks_listbox.config(yscrollcommand=tracks_scroll.set)
tracks_pagination = ttk.Frame(tracks_frame)
tracks_pagination.pack(side=tk.BOTTOM, pady=5)
tracks_prev_btn = ttk.Button(tracks_pagination, text="<< Prev", command=search_tracks_prev)
tracks_prev_btn.pack(side=tk.LEFT, padx=5)
tracks_next_btn = ttk.Button(tracks_pagination, text="Next >>", command=search_tracks_next)
tracks_next_btn.pack(side=tk.LEFT, padx=5)

playlists_frame = ttk.Labelframe(results_frame, text="Playlists")
playlists_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5,0))
search_playlists_listbox = tk.Listbox(playlists_frame)
search_playlists_listbox.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
playlists_scroll = ttk.Scrollbar(playlists_frame, command=search_playlists_listbox.yview)
playlists_scroll.pack(side=tk.RIGHT, fill=tk.Y)
search_playlists_listbox.config(yscrollcommand=playlists_scroll.set)
playlists_pagination = ttk.Frame(playlists_frame)
playlists_pagination.pack(side=tk.BOTTOM, pady=5)
playlists_prev_btn = ttk.Button(playlists_pagination, text="<< Prev", command=search_playlists_prev)
playlists_prev_btn.pack(side=tk.LEFT, padx=5)
playlists_next_btn = ttk.Button(playlists_pagination, text="Next >>", command=search_playlists_next)
playlists_next_btn.pack(side=tk.LEFT, padx=5)

convert_search_btn = ttk.Button(search_tab, text="Convert Selected", command=convert_search_selection)
convert_search_btn.pack(pady=10)

# ----- TAB 2: ACCOUNT LOOKUP -----
account_tab = ttk.Frame(notebook)
notebook.add(account_tab, text="Account Lookup")
account_frame = ttk.Frame(account_tab, padding="10")
account_frame.pack(fill=tk.X)
account_label = ttk.Label(account_frame, text="Account ID/URL or Playlist URL:", font=("Segoe UI", 11))
account_label.pack(side=tk.LEFT)
account_entry = ttk.Entry(account_frame, width=30)
account_entry.pack(side=tk.LEFT, padx=10)
load_account_btn = ttk.Button(account_frame, text="Load Account/Playlist", command=load_account_data)
load_account_btn.pack(side=tk.LEFT, padx=5)
login_btn = ttk.Button(account_frame, text="Login (for Liked Songs)", command=user_login)
login_btn.pack(side=tk.LEFT, padx=5)
login_status_label = ttk.Label(account_frame, textvariable=login_status_var)
login_status_label.pack(side=tk.LEFT, padx=10)

account_results_frame = ttk.Frame(account_tab, padding="10")
account_results_frame.pack(fill=tk.BOTH, expand=True)
acc_playlists_frame = ttk.Labelframe(account_results_frame, text="Account Playlists")
acc_playlists_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,5))
account_playlists_listbox = tk.Listbox(acc_playlists_frame)
account_playlists_listbox.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
acc_playlists_scroll = ttk.Scrollbar(acc_playlists_frame, command=account_playlists_listbox.yview)
acc_playlists_scroll.pack(side=tk.RIGHT, fill=tk.Y)
account_playlists_listbox.config(yscrollcommand=acc_playlists_scroll.set)
acc_playlists_pagination = ttk.Frame(acc_playlists_frame)
acc_playlists_pagination.pack(side=tk.BOTTOM, pady=5)
acc_playlists_prev_btn = ttk.Button(acc_playlists_pagination, text="<< Prev", command=account_playlists_prev)
acc_playlists_prev_btn.pack(side=tk.LEFT, padx=5)
acc_playlists_next_btn = ttk.Button(acc_playlists_pagination, text="Next >>", command=account_playlists_next)
acc_playlists_next_btn.pack(side=tk.LEFT, padx=5)

# Bind double-click on account playlists to show tracks.
account_playlists_listbox.bind("<Double-Button-1>", lambda event: show_playlist_tracks_by_id(
    parse_spotify_id_from_url(account_entry.get(), "playlist"),
    account_playlists_listbox.get(account_playlists_listbox.curselection())
))

acc_liked_frame = ttk.Labelframe(account_results_frame, text="Liked Songs")
acc_liked_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5,0))
account_liked_listbox = tk.Listbox(acc_liked_frame)
account_liked_listbox.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
acc_liked_scroll = ttk.Scrollbar(acc_liked_frame, command=account_liked_listbox.yview)
acc_liked_scroll.pack(side=tk.RIGHT, fill=tk.Y)
account_liked_listbox.config(yscrollcommand=acc_liked_scroll.set)
acc_liked_pagination = ttk.Frame(acc_liked_frame)
acc_liked_pagination.pack(side=tk.BOTTOM, pady=5)
acc_liked_prev_btn = ttk.Button(acc_liked_pagination, text="<< Prev", command=account_liked_prev)
acc_liked_prev_btn.pack(side=tk.LEFT, padx=5)
acc_liked_next_btn = ttk.Button(acc_liked_pagination, text="Next >>", command=account_liked_next)
acc_liked_next_btn.pack(side=tk.LEFT, padx=5)

account_convert_btn = ttk.Button(account_tab, text="Convert Selected", command=convert_account_selection)
account_convert_btn.pack(pady=10)

status_bar = ttk.Label(root, textvariable=status_var, relief=tk.SUNKEN, anchor=tk.W)
status_bar.pack(side=tk.BOTTOM, fill=tk.X)

root.mainloop()
