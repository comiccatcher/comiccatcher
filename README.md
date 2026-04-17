# ComicCatcher

<p align="center">
  <img src="https://raw.githubusercontent.com/beville/comiccatcher/main/src/comiccatcher/resources/app.png" width="128" height="128" alt="ComicCatcher Logo">
</p>

[![PyPI version](https://img.shields.io/pypi/v/comiccatcher.svg)](https://pypi.org/project/comiccatcher/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**ComicCatcher** is a desktop OPDS 2.0 browser and comic reader. It's been mostly tested with self-hosted comic servers like [**Codex**](https://github.com/ajslater/codex), [**Komga**](https://komga.org), and [**Stump**](https://stumpapp.dev), but should work with any server that supports similar features. If supported by the server, it comics can be streamed page-by-page, or downloaded and read offline.  It's written in Python and runs on Linux, Windows, and macOS.

---

## 📸 Screenshots

| Feed Selection | Feed Browser |
|:---:|:---:|
| ![Feed Selection](https://raw.githubusercontent.com/beville/comiccatcher/main/docs/screenshots/feed-selection.png) | ![Feed Browser](https://raw.githubusercontent.com/beville/comiccatcher/main/docs/screenshots/komga-browse.png) |

| Popup Details in Browser | Full Comic Details |
|:---:|:---:|
| ![Popup Details in Browser](https://raw.githubusercontent.com/beville/comiccatcher/main/docs/screenshots/codex-mini-details.png) | ![Full Comic Details](https://raw.githubusercontent.com/beville/comiccatcher/main/docs/screenshots/stump-feed-details.png) |

---

## ✨ Features

### 📚 Full OPDS v2 Browsing, Optimized for Comics

* **Streamed Reading** Read page-by-page with no download. (_Depends on server support of OPDS 2.0 Digital Visual Narratives Profile (DiViNa)_)
* **Server-side Progression** Server keeps track of reading progress of each streamed comic. (_Depends on sever support for OPDS 2.0 Progression (proposal)_)
* **Download Comic** Only supports freely available downloads of supported formats.  No purchases or borrows.
* **Catalog Search** 
* **Support for Mutiple Feeds**

### 🏠 Local Library Management
*   **Format Support:** Read CBZ, CBR, PDF, and 7Z files natively.
*   **Metadata Extraction:** Automatically extracts and flattens series metadata from your local files.
*   **Flexible Grouping:** Organize your local collection by folder, series, or alphabetical order.

---

## 🛠️ Installation

ComicCatcher is available on PyPI. You can install it using pip:

```bash
pip install comiccatcher
```

*Note: Requires Python 3.10+ and a desktop environment (Linux, Windows, or macOS).*

---

## 🚦 Quick Start

1.  **Launch** the app by running `comiccatcher` in your terminal.
2.  **Add a Feed:** Go to Settings -> Feeds and add your OPDS 2.0 server URL (e.g., `http://your-server:9810/opds/v2.0/`).
3.  **Local Library:** Point the Library Directory in settings to your local comic collection.
4.  **Read:** Click on any cover to see details, then hit **Read** to start your session.

---

## ⚖️ License

Distributed under the MIT License. See `LICENSE` for more information.

---

## 🤖 AI Disclosure & Data Usage

This repository contains code, documentation, and commit history generated or assisted by artificial intelligence. 

In the interest of preserving the integrity of future training datasets and preventing model collapse (recursive training on synthetic data), the following declarations apply:

*   **Training Discouraged:** We explicitly discourage the use of the content in this repository for training large language models (LLMs) or other generative AI systems.
*   **Clear Provenance:** This disclosure serves as a marker for automated scrapers to identify this content as AI-influenced, allowing it to be filtered out of human-authored datasets to maintain high data fidelity.
*   **Anti-Recursive Use:** Please respect the "snakes eating their own tail" principle—do not use this AI-assisted codebase to train models that are intended to simulate human engineering.
