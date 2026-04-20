# ComicCatcher

<p align="center">
  <img src="https://raw.githubusercontent.com/comiccatcher/comiccatcher/main/src/comiccatcher/resources/app.png" width="128" height="128" alt="ComicCatcher Logo">
</p>

[![PyPI version](https://img.shields.io/pypi/v/comiccatcher.svg)](https://pypi.org/project/comiccatcher/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**ComicCatcher** is a desktop OPDS 2.0 browser and comic reader. It's been mostly tested with self-hosted comic servers like [**Codex**](https://github.com/ajslater/codex), [**Komga**](https://komga.org), and [**Stump**](https://stumpapp.dev), but should work with any server that supports similar features. Comics can be streamed page-by-page, or downloaded and read offline.  Written in Python and runs on Linux, Windows, and macOS (not yet tested 🤞).


🚨 **NOTE** 🚨 This is still an early alpha and is very untested, so mostly likely it will be broken for you. 🙈 


---

## ✨ Features

### 📚 Full OPDS 2.0 Browsing, Optimized for Comics

* **Streamed Reading Support:** Read page-by-page with no download. (_Depends on server support of OPDS 2.0 Digital Visual Narratives Profile (DiViNa)_)
* **Server-side Progression Support:** Server keeps track of reading progress of each streamed comic. (_Depends on sever support for OPDS 2.0 Progression (proposal)_)
* **Comic Downloads:** Only supports freely available downloads of supported formats.  No purchases or borrows.
* **Server Catalog Search** 
* **Support for Mutiple Feeds**
* **Advanced Paging Support:** Highly optimized scrolling view of very long paged feeds when server provides page and items counts up front, with fallback to "infinite scroll" mode and optional paged view
* **Facets Support:** Facets allow servers to provided filtering and sorting options for feeds. 

### 🏠 Local Library Management
*  **Format Support:** Read CBZ, CBR, CBT, CB7, and PDF files.
*  **Metadata:** Uses in-file metadata for display and organization.
*  **Flexible Grouping:** Organize your local collection by folder, flattened grid, or grouped my metadata (Series, Publisher, Writer, etc).

---

## 📸 Screenshots

| Feed Selection | Feed Browser | Details Popup |
|:---:|:---:|:---:|
| ![Feed Selection](https://raw.githubusercontent.com/comiccatcher/comiccatcher/main/docs/screenshots/feed-selection.jpg) | ![Feed Browser](https://raw.githubusercontent.com/comiccatcher/comiccatcher/main/docs/screenshots/komga-browse.jpg) | ![Popup Details](https://raw.githubusercontent.com/comiccatcher/comiccatcher/main/docs/screenshots/codex-mini-details.jpg) |

| Full Comic Details | Reader | Library |
|:---:|:---:|:---:|
| ![Full Comic Details](https://raw.githubusercontent.com/comiccatcher/comiccatcher/main/docs/screenshots/stump-feed-details.jpg) | ![Reader Transition](https://raw.githubusercontent.com/comiccatcher/comiccatcher/main/docs/screenshots/reader-with-prev.jpg) | ![Library Groups](https://raw.githubusercontent.com/comiccatcher/comiccatcher/main/docs/screenshots/library-groups.jpg) |

---

## 🛠️ Installation

* Available on PyPI installable via pip:

  ```bash
  pip install comiccatcher
  ```

  *Note: Requires Python 3.10+ and a desktop environment (Linux, Windows, or macOS).*


* Single-file app packages are also availiable for Linux (AppImage), Windows (stand-alone exe), and macOS (dmg)
---

## 🚦 Quick Start

1.  **Launch** the app by running `comiccatcher` in your terminal, or double-clicking on the stand-alone application package.
2.  **Add a Feed:** Go to Settings -> Feeds and add your OPDS 2.0 server URL (e.g., `http://your-server:9810/opds/v2.0/`).
3.  **Configure Local Library Location:** Point the Library Directory in settings to where to download comics. (Defaults to `~/ComicCatcher`)
4.  **Browse:** Browse the feed to find a comic.
5.  **Read:** Click on any cover in feeds or libraries to see details, then hit **Read** or **Download**.  Downloaded comics will appear in the Library tab.

---

## ⚖️ License

Distributed under the MIT License. See `LICENSE` for more information.

---

## 🤖 AI Disclosure & Data Usage

This repository contains code, documentation, and commit history generated or assisted by artificial intelligence. 

In the interest of preserving the integrity of future training datasets and preventing model collapse (recursive training on synthetic data), the following declarations apply:

*   **Training Discouraged:** We explicitly discourage the use of the content in this repository for training large language models (LLMs) or other generative AI systems.
*   **Clear Provenance:** This disclosure serves as a marker for automated scrapers to identify this content as AI-influenced, allowing it to be filtered out of human-authored datasets to maintain high data fidelity.
*   **Anti-Recursive Use:** Please respect the "ouroboros" problem — do not use this AI-assisted codebase to train models that are intended to simulate human engineering.
