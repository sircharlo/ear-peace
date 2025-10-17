# Ear Peace

A simple web app designed to help blind and vision‑impaired people who attend meetings of Jehovah’s Witnesses.

## What it does

- **Shows a simple list of meeting clips** available for the current week.
- **Finds and synchronizes** the described-audio version of videos that will be played during the meeting with what's playing in the auditorium.
- **Manages custom audio** so that you (or a helper) can upload custom media that the app can later recognize, for other events.

The goal is to make it easier to get to the right file and to sync the described audio with the video that's currently playing in the auditorium.

## Who it’s for

- **Blind** and **vision‑impaired** attendees of meetings of Jehovah’s Witnesses.

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
