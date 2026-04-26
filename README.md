# Serviq - Service Booking Platform

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-3.1.3-green.svg)](https://flask.palletsprojects.com/)
[![Render](https://img.shields.io/badge/deployed%20on-Render-purple.svg)](https://render.com)

**Serviq** is a full‑stack web application that connects customers with verified service providers. Book electricians, plumbers, carpenters, and more – all at your doorstep. Built with Flask, SQLite/PostgreSQL, and modern front‑end technologies.

🔗 **Live Demo:** [https://serviq.onrender.com](https://serviq.onrender.com) *(Replace with your actual Render URL after deployment)*

---

## 📋 Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Screenshots](#screenshots)
- [Installation & Setup](#installation--setup)
- [Environment Variables](#environment-variables)
- [Database Setup](#database-setup)
- [Running the App](#running-the-app)
- [Deployment](#deployment)
- [Project Structure](#project-structure)
- [API Endpoints](#api-endpoints)
- [Testing](#testing)
- [Future Improvements](#future-improvements)
- [Contributing](#contributing)
- [License](#license)

---

## ✨ Features

### For Customers
- 🔍 Search & filter service providers by service, city, price, rating, and location
- 📅 Book available time slots
- 💳 Secure online payments (Razorpay integration)
- ⭐ Rate and review providers after service completion
- 💬 Real‑time chat with providers
- 📍 Manage multiple addresses

### For Service Providers
- 📝 Register and wait for admin approval
- 🗓️ Manage your own time slots (availability)
- ✅ Update booking status (confirm, complete, cancel)
- 💰 View earnings and transaction history
- ⭐ Respond to customer reviews

### For Admin
- 👥 Manage users (customers & providers)
- ✅ Approve or reject provider registrations
- 🛠️ Add, edit, or delete service categories
- 📊 View dashboard with key metrics (revenue, bookings, pending approvals)
- 💬 Oversee all bookings and transactions

### General
- 🔐 Secure authentication (password hashing, OTP via SMS)
- 📱 Fully responsive design (Bootstrap 5)
- 🗺️ Google Maps integration for provider location
- 🌐 Deployed and ready for production

---

## 🛠️ Tech Stack

| Category       | Technologies                                                                 |
|----------------|------------------------------------------------------------------------------|
| **Backend**    | Python 3.11, Flask, Flask‑SQLAlchemy, Flask‑Login, Flask‑SocketIO           |
| **Frontend**   | HTML5, CSS3, Bootstrap 5, JavaScript, Jinja2 templates                      |
| **Database**   | SQLite (development) / PostgreSQL (production)                              |
| **APIs**       | Razorpay (Payments), Twilio (SMS), Google Maps (Places, Geocoding)          |
| **Deployment** | Render (PaaS), Gunicorn + Eventlet                                           |
| **Real‑time**  | Socket.IO for chat                                                          |

---

## 📸 Screenshots

> *Add screenshots of your app here. You can place images in a `screenshots/` folder and link them.*

![Homepage](screenshots/homepage.png)
![Customer Dashboard](screenshots/customer-dashboard.png)
![Provider Dashboard](screenshots/provider-dashboard.png)
![Admin Dashboard](screenshots/admin-dashboard.png)
![Booking Page](screenshots/booking.png)

*(Replace with actual screenshot paths after you take them)*

---

## 🚀 Installation & Setup

### Prerequisites
- Python 3.11 or higher
- Git
- (Optional) Virtual environment (recommended)

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/serviq.git
cd serviq