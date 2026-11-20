// Su Windows non apre la finestra nera del terminale insieme all'app
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    video_downloader_lib::avvia()
}
