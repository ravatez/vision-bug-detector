# Vision Bug Detector (AI-Powered UI Regression System)

## 🚀 Overview
Vision Bug Detector is an AI-powered system that detects visual bugs in UI or game screens by comparing screenshots and generating intelligent reports.

## ❓ Problem Statement
Manual UI testing is:
- Time-consuming
- Error-prone
- Not scalable

Small visual bugs like alignment issues, missing elements, or color changes are often missed.

## 💡 Solution
This system automates UI testing by:
1. Capturing screenshots
2. Comparing images
3. Detecting differences
4. (Future) Using AI to explain issues

## 🧩 Current Progress (Day 1)
✅ Screenshot capture system using Playwright  
✅ Structured test case storage  
✅ Automated baseline and current image capture  

## 📁 Project Structure
```
vision-bug-detector/
├── data/screenshots/
├── scripts/capture.py
├── src/
├── requirements.txt
└── README.md
```

## ⚙️ Setup

```bash
pip install -r requirements.txt
playwright install
```
## ▶️ Run
python scripts/capture.py

## 📌 Next Steps
- Image comparison using OpenCV
- Highlight visual differences
- Add AI-based bug explanation
- Build dashboard for visualization

## 🧠 Tech Stack
- Python
- Playwright
- (Upcoming) OpenCV
- (Upcoming) LLaVA + Ollama