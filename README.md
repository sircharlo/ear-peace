# Ear Peace

A simple web app designed to help blind and vision‑impaired people who attend Jehovah’s Witnesses meetings.

## What it does (in simple terms)

- **Finds meeting audio quickly**: The app can take a short audio sample and try to match it to items in a prepared list of clips for the week.
- **Shows the week’s clips**: See a simple list of clips available for the current week.
- **Manages custom audio**: You (or a helper) can upload custom media that the app can later recognize.

The goal is to make it easier to get to the right audio without searching through screens.

## Who it’s for

- **Blind** and **vision‑impaired** attendees of JW meetings.
- Anyone assisting them who wants a very simple way to jump to the right audio clip.

## Current status

- **Work in progress.** Features may change, and things may break.
- Your **feedback** is welcome. Pull requests are also welcome.

## How to run (local)

- Requirements: **Docker** and **Docker Compose**.
- Start the app:
  ```bash
  docker compose up -d --build
  ```
- Open the frontend: `http://localhost:8080`
- Backend API (for reference): `http://localhost:8000`

## Accessibility

- We aim for simple layouts, clear labels, and keyboard/screen‑reader friendliness.
- Please tell us what helps you most. Real‑world feedback will guide improvements.

## Feedback and contributions

- **Feedback**: Open an issue describing what worked, what didn’t, and what you’d like to see.
- **Pull requests**: Small, focused PRs are appreciated. Accessibility improvements are a priority.

## Privacy note

- Audio samples used for matching are sent to the backend only to perform the match and are not intended for sharing.
- This is a local app; please still use it with discretion and in harmony with local laws and guidelines.
