"""
Auto News Scraper - Web Dashboard
Flask-based settings UI for managing sources, filters, and viewing activity.
"""

import asyncio
import logging
import os
import threading
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from flask_cors import CORS

import config
from database import get_recent_posts, get_activity_log, get_stats, init_db

logger = logging.getLogger("dashboard")

app = Flask(__name__)
app.secret_key = config.DASHBOARD_SECRET_KEY
CORS(app)


# ─── HTML Template ────────────────────────────────────────────────────────────

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Auto News Scraper</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        /* ── Theme Variables ─────────────────────────────── */
        [data-theme="dark"] {
            --bg-body: #0c0c14;
            --bg-surface: #13131f;
            --bg-card: rgba(22, 22, 38, 0.8);
            --bg-card-hover: rgba(28, 28, 48, 0.9);
            --bg-input: rgba(30, 30, 52, 0.9);
            --bg-header: rgba(13, 13, 20, 0.85);
            --text-primary: #eaeaf4;
            --text-secondary: #8888a8;
            --text-tertiary: #5a5a78;
            --border: rgba(255, 255, 255, 0.06);
            --border-hover: rgba(255, 255, 255, 0.12);
            --shadow-card: 0 2px 16px rgba(0, 0, 0, 0.3);
            --shadow-elevated: 0 8px 32px rgba(0, 0, 0, 0.4);
            --glass-blur: blur(24px);
            --theme-icon: "☀️";
            --code-bg: rgba(255, 255, 255, 0.05);
        }

        [data-theme="light"] {
            --bg-body: #f4f5f9;
            --bg-surface: #ffffff;
            --bg-card: rgba(255, 255, 255, 0.85);
            --bg-card-hover: rgba(255, 255, 255, 0.95);
            --bg-input: rgba(240, 241, 248, 0.9);
            --bg-header: rgba(255, 255, 255, 0.88);
            --text-primary: #1a1a2e;
            --text-secondary: #6b6b8d;
            --text-tertiary: #9999b3;
            --border: rgba(0, 0, 0, 0.07);
            --border-hover: rgba(0, 0, 0, 0.14);
            --shadow-card: 0 2px 12px rgba(0, 0, 0, 0.06);
            --shadow-elevated: 0 8px 32px rgba(0, 0, 0, 0.1);
            --glass-blur: blur(24px);
            --theme-icon: "🌙";
            --code-bg: rgba(0, 0, 0, 0.04);
        }

        /* ── Platform Colors (always same) ───────────────── */
        :root {
            --telegram: #2AABEE;
            --telegram-dim: rgba(42, 171, 238, 0.12);
            --telegram-glow: rgba(42, 171, 238, 0.25);
            --x-color: #000000;
            --x-dim: rgba(120, 120, 140, 0.12);
            --facebook: #1877F2;
            --facebook-dim: rgba(24, 119, 242, 0.12);
            --facebook-glow: rgba(24, 119, 242, 0.25);
            --success: #10b981;
            --success-dim: rgba(16, 185, 129, 0.12);
            --warning: #f59e0b;
            --warning-dim: rgba(245, 158, 11, 0.12);
            --error: #ef4444;
            --error-dim: rgba(239, 68, 68, 0.12);
            --accent: #6366f1;
            --accent-dim: rgba(99, 102, 241, 0.12);
            --accent-glow: rgba(99, 102, 241, 0.2);
        }

        [data-theme="light"] {
            --x-color: #14171a;
        }

        /* ── Global Reset ────────────────────────────────── */
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-body);
            color: var(--text-primary);
            min-height: 100vh;
            line-height: 1.6;
            transition: background 0.35s ease, color 0.35s ease;
            -webkit-font-smoothing: antialiased;
        }

        /* ── Header ──────────────────────────────────────── */
        .header {
            background: var(--bg-header);
            backdrop-filter: var(--glass-blur);
            -webkit-backdrop-filter: var(--glass-blur);
            border-bottom: 1px solid var(--border);
            padding: 0 2rem;
            height: 56px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .header-left {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .logo {
            width: 32px; height: 32px;
            background: linear-gradient(135deg, var(--telegram) 0%, var(--accent) 50%, var(--facebook) 100%);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
        }

        .header-title {
            font-size: 1.05rem;
            font-weight: 600;
            letter-spacing: -0.02em;
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .status-pill {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 4px 12px;
            border-radius: 100px;
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            background: var(--success-dim);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }

        .status-dot {
            width: 6px; height: 6px;
            border-radius: 50%;
            background: var(--success);
            animation: pulse 2.5s ease-in-out infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }
            50% { opacity: 0.6; box-shadow: 0 0 0 4px rgba(16, 185, 129, 0); }
        }

        .theme-toggle {
            width: 36px; height: 36px;
            border-radius: 10px;
            border: 1px solid var(--border);
            background: var(--bg-card);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1rem;
            transition: all 0.25s;
        }

        .theme-toggle:hover {
            border-color: var(--border-hover);
            background: var(--bg-card-hover);
            transform: scale(1.05);
        }

        /* ── Container ───────────────────────────────────── */
        .container {
            max-width: 960px;
            margin: 0 auto;
            padding: 1.5rem 1.5rem 3rem;
        }

        /* ── Stats Grid ──────────────────────────────────── */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 0.75rem;
            margin-bottom: 1.5rem;
        }

        .stat-card {
            background: var(--bg-card);
            backdrop-filter: var(--glass-blur);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1rem 1.1rem;
            transition: all 0.25s;
            position: relative;
            overflow: hidden;
        }

        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 2px;
            border-radius: 12px 12px 0 0;
        }

        .stat-card.total::before { background: linear-gradient(90deg, var(--accent), var(--telegram)); }
        .stat-card.today::before { background: var(--success); }
        .stat-card.tg::before { background: var(--telegram); }
        .stat-card.x-card::before { background: var(--text-secondary); }

        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-elevated);
            border-color: var(--border-hover);
        }

        .stat-label {
            font-size: 0.68rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-tertiary);
            margin-bottom: 0.25rem;
        }

        .stat-value {
            font-size: 1.6rem;
            font-weight: 700;
            font-variant-numeric: tabular-nums;
        }

        .stat-card.total .stat-value { color: var(--accent); }
        .stat-card.today .stat-value { color: var(--success); }
        .stat-card.tg .stat-value { color: var(--telegram); }
        .stat-card.x-card .stat-value { color: var(--text-primary); }

        /* ── Tabs ────────────────────────────────────────── */
        .tabs {
            display: flex;
            gap: 2px;
            margin-bottom: 1.25rem;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 3px;
            overflow-x: auto;
        }

        .tab {
            flex: 1;
            padding: 0.55rem 0.8rem;
            background: transparent;
            color: var(--text-secondary);
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.8rem;
            font-weight: 500;
            font-family: inherit;
            transition: all 0.2s;
            white-space: nowrap;
            text-align: center;
        }

        .tab:hover { color: var(--text-primary); background: rgba(255,255,255,0.03); }

        .tab.active {
            color: var(--text-primary);
            background: var(--bg-input);
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            font-weight: 600;
        }

        [data-theme="light"] .tab:hover { background: rgba(0,0,0,0.03); }
        [data-theme="light"] .tab.active { background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }

        .tab-content { display: none; animation: fadeIn 0.3s ease; }
        .tab-content.active { display: block; }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* ── Card ────────────────────────────────────────── */
        .card {
            background: var(--bg-card);
            backdrop-filter: var(--glass-blur);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 1.25rem;
            margin-bottom: 1rem;
            transition: all 0.25s;
        }

        .card:hover {
            border-color: var(--border-hover);
            box-shadow: var(--shadow-card);
        }

        .card-header {
            display: flex;
            align-items: center;
            gap: 0.6rem;
            margin-bottom: 0.9rem;
        }

        .card-icon {
            width: 32px; height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.95rem;
            flex-shrink: 0;
        }

        .card-icon.tg { background: var(--telegram-dim); }
        .card-icon.x { background: var(--x-dim); }
        .card-icon.fb { background: var(--facebook-dim); }
        .card-icon.filter { background: var(--accent-dim); }
        .card-icon.settings { background: var(--warning-dim); }
        .card-icon.key { background: var(--success-dim); }

        .card-title {
            font-size: 0.9rem;
            font-weight: 600;
        }

        .card-subtitle {
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-top: -0.4rem;
            margin-bottom: 0.8rem;
        }

        /* ── Form Elements ───────────────────────────────── */
        .input-row {
            display: flex;
            gap: 0.4rem;
            margin-bottom: 0.25rem;
        }

        input[type="text"], input[type="password"], select {
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.55rem 0.85rem;
            color: var(--text-primary);
            font-size: 0.82rem;
            font-family: inherit;
            width: 100%;
            outline: none;
            transition: all 0.2s;
        }

        input[type="text"]:focus, input[type="password"]:focus, select:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }

        input::placeholder { color: var(--text-tertiary); }

        .form-label {
            display: block;
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-bottom: 0.3rem;
            font-weight: 500;
        }

        .form-group { margin-bottom: 0.8rem; }

        /* ── Buttons ─────────────────────────────────────── */
        .btn {
            padding: 0.55rem 1rem;
            border-radius: 8px;
            border: 1px solid transparent;
            cursor: pointer;
            font-size: 0.8rem;
            font-weight: 600;
            font-family: inherit;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            white-space: nowrap;
        }

        .btn-primary {
            background: var(--accent);
            color: white;
        }
        .btn-primary:hover { background: #5558e6; transform: translateY(-1px); }

        .btn-save {
            background: var(--success);
            color: white;
        }
        .btn-save:hover { background: #0ea572; transform: translateY(-1px); }

        .btn-ghost {
            background: transparent;
            color: var(--text-secondary);
            border: 1px solid var(--border);
        }
        .btn-ghost:hover { color: var(--text-primary); border-color: var(--border-hover); background: var(--bg-input); }

        .btn-sm {
            padding: 0.35rem 0.65rem;
            font-size: 0.72rem;
            border-radius: 6px;
        }

        /* ── Tags ────────────────────────────────────────── */
        .tags {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
            margin-top: 0.5rem;
        }

        .tag {
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 0.25rem 0.6rem;
            font-size: 0.76rem;
            display: flex;
            align-items: center;
            gap: 0.4rem;
            font-weight: 500;
            transition: all 0.15s;
        }

        .tag:hover { border-color: var(--border-hover); }

        .tag .remove {
            cursor: pointer;
            color: var(--error);
            font-size: 0.65rem;
            opacity: 0.5;
            transition: opacity 0.15s;
            line-height: 1;
        }

        .tag .remove:hover { opacity: 1; }

        /* ── Toggle Switch ───────────────────────────────── */
        .setting-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.7rem 0;
            border-bottom: 1px solid var(--border);
        }

        .setting-row:last-child { border-bottom: none; }

        .setting-info { flex: 1; }
        .setting-label { font-weight: 500; font-size: 0.85rem; }
        .setting-desc { font-size: 0.73rem; color: var(--text-secondary); }

        .toggle {
            position: relative;
            width: 42px;
            height: 24px;
            flex-shrink: 0;
        }

        .toggle input { opacity: 0; width: 0; height: 0; }

        .toggle .slider {
            position: absolute;
            inset: 0;
            background: var(--bg-input);
            border-radius: 24px;
            cursor: pointer;
            transition: 0.3s;
            border: 1px solid var(--border);
        }

        .toggle .slider::before {
            content: "";
            position: absolute;
            width: 18px; height: 18px;
            left: 2px; bottom: 2px;
            background: var(--text-secondary);
            border-radius: 50%;
            transition: 0.3s;
        }

        .toggle input:checked + .slider { background: var(--accent); border-color: var(--accent); }
        .toggle input:checked + .slider::before { transform: translateX(18px); background: white; }

        /* ── Collapsible API Sections ────────────────────── */
        .accordion {
            border: 1px solid var(--border);
            border-radius: 10px;
            overflow: hidden;
            margin-bottom: 0.6rem;
            transition: border-color 0.2s;
        }

        .accordion:hover { border-color: var(--border-hover); }

        .accordion-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.75rem 1rem;
            background: var(--bg-input);
            cursor: pointer;
            user-select: none;
            transition: background 0.2s;
        }

        .accordion-header:hover { background: var(--bg-card-hover); }

        .accordion-header-left {
            display: flex;
            align-items: center;
            gap: 0.6rem;
        }

        .accordion-icon {
            width: 28px; height: 28px;
            border-radius: 7px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.85rem;
            flex-shrink: 0;
        }

        .accordion-title {
            font-size: 0.82rem;
            font-weight: 600;
        }

        .accordion-badge {
            font-size: 0.65rem;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 100px;
        }

        .accordion-badge.ok { background: var(--success-dim); color: var(--success); }
        .accordion-badge.missing { background: var(--error-dim); color: var(--error); }

        .accordion-chevron {
            font-size: 0.7rem;
            color: var(--text-tertiary);
            transition: transform 0.3s ease;
            margin-left: 0.5rem;
        }

        .accordion.open .accordion-chevron { transform: rotate(180deg); }

        .accordion-body {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.35s ease, padding 0.35s ease;
            padding: 0 1rem;
        }

        .accordion.open .accordion-body {
            max-height: 500px;
            padding: 0.8rem 1rem 1rem;
        }

        .api-field { margin-bottom: 0.6rem; }

        .api-field:last-child { margin-bottom: 0; }

        .api-field label {
            display: block;
            font-size: 0.72rem;
            color: var(--text-secondary);
            margin-bottom: 0.2rem;
            font-weight: 500;
        }

        .api-hint {
            font-size: 0.7rem;
            color: var(--text-tertiary);
            margin-top: 0.15rem;
        }

        .api-hint a { color: var(--accent); text-decoration: none; }
        .api-hint a:hover { text-decoration: underline; }

        /* ── Activity Log ────────────────────────────────── */
        .log-entries {
            max-height: 420px;
            overflow-y: auto;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.73rem;
        }

        .log-entry {
            padding: 0.35rem 0.5rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            gap: 0.6rem;
            align-items: baseline;
        }

        .log-entry:last-child { border-bottom: none; }
        .log-entry:hover { background: rgba(255,255,255,0.02); }
        .log-entry .time { color: var(--text-tertiary); white-space: nowrap; font-size: 0.68rem; }
        .log-entry .source { color: var(--accent); min-width: 60px; font-weight: 500; }
        .log-entry .msg { color: var(--text-secondary); }
        .log-entry.error .msg { color: var(--error); }
        .log-entry.warning .msg { color: var(--warning); }

        [data-theme="light"] .log-entry:hover { background: rgba(0,0,0,0.02); }

        /* ── Recent Posts ────────────────────────────────── */
        .post-item {
            padding: 0.65rem 0.5rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            gap: 0.75rem;
            align-items: flex-start;
        }

        .post-item:last-child { border-bottom: none; }

        .post-icon {
            width: 30px; height: 30px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.85rem;
            flex-shrink: 0;
        }

        .post-icon.tg { background: var(--telegram-dim); }
        .post-icon.x { background: var(--x-dim); }

        .post-body { flex: 1; min-width: 0; }
        .post-title { font-weight: 500; font-size: 0.82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .post-meta { color: var(--text-tertiary); font-size: 0.7rem; margin-top: 1px; }
        .post-badges { display: flex; gap: 0.25rem; margin-top: 0.3rem; }

        .badge {
            font-size: 0.6rem;
            padding: 1px 7px;
            border-radius: 4px;
            font-weight: 600;
            letter-spacing: 0.03em;
        }

        .badge.tg { background: var(--telegram-dim); color: var(--telegram); }
        .badge.fb { background: var(--facebook-dim); color: var(--facebook); }

        /* ── Toast ───────────────────────────────────────── */
        .toast {
            position: fixed;
            bottom: 1.5rem;
            right: 1.5rem;
            padding: 0.65rem 1.2rem;
            border-radius: 10px;
            color: white;
            font-weight: 500;
            font-size: 0.82rem;
            z-index: 1000;
            opacity: 0;
            transform: translateY(12px) scale(0.96);
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            pointer-events: none;
            backdrop-filter: blur(12px);
        }

        .toast.show { opacity: 1; transform: translateY(0) scale(1); }
        .toast.success { background: rgba(16, 185, 129, 0.92); }
        .toast.error { background: rgba(239, 68, 68, 0.92); }

        /* ── Empty State ─────────────────────────────────── */
        .empty-state {
            text-align: center;
            padding: 2rem 1rem;
            color: var(--text-tertiary);
            font-size: 0.82rem;
        }

        /* ── Responsive ──────────────────────────────────── */
        @media (max-width: 640px) {
            .container { padding: 1rem; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
            .header { padding: 0 1rem; }
            .tabs { gap: 1px; padding: 2px; }
            .tab { padding: 0.45rem 0.5rem; font-size: 0.72rem; }
        }

        /* ── Scrollbar ───────────────────────────────────── */
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-tertiary); }
    </style>
</head>
<body>

    <!-- Header -->
    <div class="header">
        <div class="header-left">
            <div class="logo">📰</div>
            <span class="header-title">Auto News Scraper</span>
        </div>
        <div class="header-right">
            <div class="status-pill">
                <div class="status-dot"></div>
                LIVE
            </div>
            <button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme" id="theme-btn">🌙</button>
        </div>
    </div>

    <div class="container">

        <!-- Stats -->
        <div class="stats-grid">
            <div class="stat-card total">
                <div class="stat-label">Total Forwarded</div>
                <div class="stat-value" id="stat-total">0</div>
            </div>
            <div class="stat-card today">
                <div class="stat-label">Today</div>
                <div class="stat-value" id="stat-today">0</div>
            </div>
            <div class="stat-card tg">
                <div class="stat-label">Telegram</div>
                <div class="stat-value" id="stat-telegram">0</div>
            </div>
            <div class="stat-card x-card">
                <div class="stat-label">X (Twitter)</div>
                <div class="stat-value" id="stat-x">0</div>
            </div>
        </div>

        <!-- Tabs -->
        <div class="tabs">
            <button class="tab active" onclick="switchTab('sources', this)">Sources</button>
            <button class="tab" onclick="switchTab('filters', this)">Filters</button>
            <button class="tab" onclick="switchTab('settings', this)">Settings</button>
            <button class="tab" onclick="switchTab('activity', this)">Activity</button>
            <button class="tab" onclick="switchTab('posts', this)">Posts</button>
        </div>

        <!-- ═══ Sources Tab ═══ -->
        <div id="tab-sources" class="tab-content active">
            <!-- Telegram -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon tg">📡</div>
                    <div class="card-title">Telegram Channels</div>
                </div>
                <p class="card-subtitle">Add channel usernames or IDs to monitor in real-time</p>
                <div class="input-row">
                    <input type="text" id="tg-channel-input" placeholder="e.g. duaborneo or -1001234567890">
                    <button class="btn btn-primary btn-sm" onclick="addItem('telegram_sources', 'tg-channel-input')">Add</button>
                </div>
                <div class="tags" id="tg-channel-tags"></div>
            </div>

            <!-- X Accounts -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon x">𝕏</div>
                    <div class="card-title">X Accounts</div>
                </div>
                <p class="card-subtitle">Usernames without @ — polls recent tweets periodically</p>
                <div class="input-row">
                    <input type="text" id="x-account-input" placeholder="e.g. elonmusk">
                    <button class="btn btn-primary btn-sm" onclick="addItem('x_accounts', 'x-account-input')">Add</button>
                </div>
                <div class="tags" id="x-account-tags"></div>
            </div>

            <!-- X Hashtags -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon x">#</div>
                    <div class="card-title">X Hashtags</div>
                </div>
                <p class="card-subtitle">Hashtags without # — monitors for matching tweets</p>
                <div class="input-row">
                    <input type="text" id="x-hashtag-input" placeholder="e.g. breaking">
                    <button class="btn btn-primary btn-sm" onclick="addItem('x_hashtags', 'x-hashtag-input')">Add</button>
                </div>
                <div class="tags" id="x-hashtag-tags"></div>
            </div>
        </div>

        <!-- ═══ Filters Tab ═══ -->
        <div id="tab-filters" class="tab-content">
            <div class="card">
                <div class="card-header">
                    <div class="card-icon filter">🎯</div>
                    <div class="card-title">Content Filter</div>
                </div>

                <div class="form-group">
                    <label class="form-label">Filter Mode</label>
                    <select id="filter-mode" onchange="updateFilterMode()">
                        <option value="all">All Mode — forward everything except excluded keywords</option>
                        <option value="include">Include Mode — only forward posts matching include keywords</option>
                    </select>
                </div>

                <div class="form-group">
                    <label class="form-label">Include Keywords</label>
                    <div class="input-row">
                        <input type="text" id="include-keyword-input" placeholder="Add keyword...">
                        <button class="btn btn-primary btn-sm" onclick="addItem('filter_include_keywords', 'include-keyword-input')">Add</button>
                    </div>
                    <div class="tags" id="include-keyword-tags"></div>
                </div>

                <div class="form-group">
                    <label class="form-label">Exclude Keywords — posts with these words are never forwarded</label>
                    <div class="input-row">
                        <input type="text" id="exclude-keyword-input" placeholder="Add keyword...">
                        <button class="btn btn-primary btn-sm" onclick="addItem('filter_exclude_keywords', 'exclude-keyword-input')">Add</button>
                    </div>
                    <div class="tags" id="exclude-keyword-tags"></div>
                </div>
            </div>
        </div>

        <!-- ═══ Settings Tab ═══ -->
        <div id="tab-settings" class="tab-content">

            <!-- Output Toggles -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon settings">⚙️</div>
                    <div class="card-title">Output Channels</div>
                </div>

                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-label">📡 Telegram Channel</div>
                        <div class="setting-desc">Forward posts to your Telegram channel</div>
                    </div>
                    <label class="toggle">
                        <input type="checkbox" checked disabled>
                        <span class="slider"></span>
                    </label>
                </div>

                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-label">📘 Facebook Page</div>
                        <div class="setting-desc">Also post to your Facebook page</div>
                    </div>
                    <label class="toggle">
                        <input type="checkbox" id="facebook-toggle" onchange="toggleFacebook()">
                        <span class="slider"></span>
                    </label>
                </div>
            </div>

            <!-- API Configuration (Collapsible) -->
            <div class="card" style="padding:1rem;">
                <div class="card-header" style="margin-bottom:0.6rem;">
                    <div class="card-icon key">🔑</div>
                    <div class="card-title">API Configuration</div>
                </div>
                <p style="font-size:0.73rem;color:var(--text-secondary);margin-bottom:0.8rem;">
                    Enter credentials below. Saved to <code style="background:var(--code-bg);padding:1px 5px;border-radius:4px;font-size:0.72rem;">.env</code> — restart needed after changes.
                </p>

                <!-- Telegram User -->
                <div class="accordion" id="acc-tg-user">
                    <div class="accordion-header" onclick="toggleAccordion('acc-tg-user')">
                        <div class="accordion-header-left">
                            <div class="accordion-icon" style="background:var(--telegram-dim);">📡</div>
                            <span class="accordion-title">Telegram User Client</span>
                            <span class="accordion-badge" id="badge-tg-user">—</span>
                        </div>
                        <span class="accordion-chevron">▼</span>
                    </div>
                    <div class="accordion-body">
                        <div class="api-hint" style="margin-bottom:0.5rem;">Get from <a href="https://my.telegram.org" target="_blank">my.telegram.org</a> → API Development Tools</div>
                        <div class="api-field">
                            <label>API ID</label>
                            <input type="text" id="api-tg-api-id" placeholder="e.g. 12345678">
                        </div>
                        <div class="api-field">
                            <label>API Hash</label>
                            <input type="password" id="api-tg-api-hash" placeholder="e.g. a1b2c3d4e5f6...">
                        </div>
                        <div class="api-field">
                            <label>Phone Number</label>
                            <input type="text" id="api-tg-phone" placeholder="e.g. +855123456789">
                        </div>
                    </div>
                </div>

                <!-- Telegram Bot -->
                <div class="accordion" id="acc-tg-bot">
                    <div class="accordion-header" onclick="toggleAccordion('acc-tg-bot')">
                        <div class="accordion-header-left">
                            <div class="accordion-icon" style="background:var(--telegram-dim);">🤖</div>
                            <span class="accordion-title">Telegram Bot</span>
                            <span class="accordion-badge" id="badge-tg-bot">—</span>
                        </div>
                        <span class="accordion-chevron">▼</span>
                    </div>
                    <div class="accordion-body">
                        <div class="api-hint" style="margin-bottom:0.5rem;">Get from <a href="https://t.me/BotFather" target="_blank">@BotFather</a> on Telegram</div>
                        <div class="api-field">
                            <label>Bot Token</label>
                            <input type="password" id="api-tg-bot-token" placeholder="e.g. 123456:ABC-xyz...">
                        </div>
                        <div class="api-field">
                            <label>Channel ID</label>
                            <input type="text" id="api-tg-channel-id" placeholder="e.g. -1001234567890">
                            <div class="api-hint">Forward a message from your channel to <a href="https://t.me/userinfobot" target="_blank">@userinfobot</a> to get the ID</div>
                        </div>
                    </div>
                </div>

                <!-- X API -->
                <div class="accordion" id="acc-x">
                    <div class="accordion-header" onclick="toggleAccordion('acc-x')">
                        <div class="accordion-header-left">
                            <div class="accordion-icon" style="background:var(--x-dim);">𝕏</div>
                            <span class="accordion-title">X (Twitter) API</span>
                            <span class="accordion-badge" id="badge-x">—</span>
                        </div>
                        <span class="accordion-chevron">▼</span>
                    </div>
                    <div class="accordion-body">
                        <div class="api-hint" style="margin-bottom:0.5rem;">Get from <a href="https://developer.x.com" target="_blank">developer.x.com</a> → Projects & Apps</div>
                        <div class="api-field">
                            <label>Bearer Token</label>
                            <input type="password" id="api-x-bearer" placeholder="e.g. AAAAAAAAA...">
                        </div>
                    </div>
                </div>

                <!-- Facebook -->
                <div class="accordion" id="acc-fb">
                    <div class="accordion-header" onclick="toggleAccordion('acc-fb')">
                        <div class="accordion-header-left">
                            <div class="accordion-icon" style="background:var(--facebook-dim);">📘</div>
                            <span class="accordion-title">Facebook Page</span>
                            <span class="accordion-badge" id="badge-fb">—</span>
                        </div>
                        <span class="accordion-chevron">▼</span>
                    </div>
                    <div class="accordion-body">
                        <div class="api-hint" style="margin-bottom:0.5rem;">Get from <a href="https://developers.facebook.com" target="_blank">developers.facebook.com</a> → Graph API Explorer</div>
                        <div class="api-field">
                            <label>Page Access Token</label>
                            <input type="password" id="api-fb-token" placeholder="Token with pages_manage_posts permission">
                        </div>
                        <div class="api-field">
                            <label>Page ID</label>
                            <input type="text" id="api-fb-page-id" placeholder="e.g. 123456789012345">
                        </div>
                    </div>
                </div>

                <div style="display:flex; justify-content:flex-end; margin-top:0.8rem;">
                    <button class="btn btn-save" onclick="saveApiKeys()">💾 Save API Keys</button>
                </div>
            </div>

            <!-- API Status -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background:var(--accent-dim);">📋</div>
                    <div class="card-title">Status Overview</div>
                </div>
                <div id="api-status"></div>
            </div>
        </div>

        <!-- ═══ Activity Tab ═══ -->
        <div id="tab-activity" class="tab-content">
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background:var(--accent-dim);">📋</div>
                    <div class="card-title">Activity Log</div>
                </div>
                <div class="log-entries" id="activity-log">
                    <div class="empty-state">Loading...</div>
                </div>
            </div>
        </div>

        <!-- ═══ Posts Tab ═══ -->
        <div id="tab-posts" class="tab-content">
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background:var(--success-dim);">📨</div>
                    <div class="card-title">Recently Forwarded</div>
                </div>
                <div id="recent-posts">
                    <div class="empty-state">Loading...</div>
                </div>
            </div>
        </div>

    </div>

    <!-- Toast -->
    <div class="toast" id="toast"></div>

    <script>
        let currentSettings = {};

        // ─── Theme ──────────────────────────────────────
        function toggleTheme() {
            const html = document.documentElement;
            const next = html.dataset.theme === 'dark' ? 'light' : 'dark';
            html.dataset.theme = next;
            document.getElementById('theme-btn').textContent = next === 'dark' ? '🌙' : '☀️';
            localStorage.setItem('theme', next);
        }

        (function initTheme() {
            const saved = localStorage.getItem('theme');
            if (saved) {
                document.documentElement.dataset.theme = saved;
                document.getElementById('theme-btn').textContent = saved === 'dark' ? '🌙' : '☀️';
            }
        })();

        // ─── Accordion (collapsible) ────────────────────
        function toggleAccordion(id) {
            const el = document.getElementById(id);
            el.classList.toggle('open');
        }

        // ─── Data loading ───────────────────────────────
        async function loadSettings() {
            const res = await fetch('/api/settings');
            currentSettings = await res.json();
            renderSettings();
        }

        async function loadStats() {
            const res = await fetch('/api/stats');
            const d = await res.json();
            document.getElementById('stat-total').textContent = d.total_posts || 0;
            document.getElementById('stat-today').textContent = d.posts_today || 0;
            document.getElementById('stat-telegram').textContent = d.by_source?.telegram || 0;
            document.getElementById('stat-x').textContent = d.by_source?.x || 0;
        }

        async function loadActivity() {
            const res = await fetch('/api/activity');
            const data = await res.json();
            const c = document.getElementById('activity-log');
            if (!data.length) { c.innerHTML = '<div class="empty-state">No activity yet</div>'; return; }
            c.innerHTML = data.map(e => `
                <div class="log-entry ${e.level}">
                    <span class="time">${e.timestamp}</span>
                    <span class="source">${e.source || '—'}</span>
                    <span class="msg">${e.message}</span>
                </div>
            `).join('');
        }

        async function loadPosts() {
            const res = await fetch('/api/posts');
            const data = await res.json();
            const c = document.getElementById('recent-posts');
            if (!data.length) { c.innerHTML = '<div class="empty-state">No posts forwarded yet</div>'; return; }
            c.innerHTML = data.map(p => `
                <div class="post-item">
                    <div class="post-icon ${p.source === 'telegram' ? 'tg' : 'x'}">${p.source === 'telegram' ? '📡' : '𝕏'}</div>
                    <div class="post-body">
                        <div class="post-title">${escapeHtml(p.title || 'No title')}</div>
                        <div class="post-meta">${p.sent_at} · ${p.source}</div>
                        <div class="post-badges">
                            ${p.sent_to_telegram ? '<span class="badge tg">Telegram</span>' : ''}
                            ${p.sent_to_facebook ? '<span class="badge fb">Facebook</span>' : ''}
                        </div>
                    </div>
                </div>
            `).join('');
        }

        // ─── Render ─────────────────────────────────────
        function renderSettings() {
            renderTags('tg-channel-tags', currentSettings.telegram_sources || [], 'telegram_sources');
            renderTags('x-account-tags', currentSettings.x_accounts || [], 'x_accounts');
            renderTags('x-hashtag-tags', currentSettings.x_hashtags || [], 'x_hashtags');
            renderTags('include-keyword-tags', currentSettings.filter_include_keywords || [], 'filter_include_keywords');
            renderTags('exclude-keyword-tags', currentSettings.filter_exclude_keywords || [], 'filter_exclude_keywords');
            document.getElementById('filter-mode').value = currentSettings.filter_mode || 'all';
            document.getElementById('facebook-toggle').checked = currentSettings.facebook_posting_enabled || false;
            loadApiStatus();
            loadApiKeys();
        }

        function renderTags(cid, items, key) {
            const c = document.getElementById(cid);
            const prefix = key === 'x_accounts' ? '@' : key === 'x_hashtags' ? '#' : '';
            c.innerHTML = items.map((item, i) => `
                <div class="tag">${prefix}${item}<span class="remove" onclick="removeItem('${key}', ${i})">✕</span></div>
            `).join('');
        }

        // ─── Actions ────────────────────────────────────
        async function addItem(key, inputId) {
            const input = document.getElementById(inputId);
            let v = input.value.trim().replace(/^[@#]/, '');
            if (!v) return;
            if (!currentSettings[key]) currentSettings[key] = [];
            if (currentSettings[key].includes(v)) { showToast('Already added!', 'error'); return; }
            currentSettings[key].push(v);
            await saveSettings();
            input.value = '';
            input.focus();
        }

        async function removeItem(key, i) {
            currentSettings[key].splice(i, 1);
            await saveSettings();
        }

        async function updateFilterMode() {
            currentSettings.filter_mode = document.getElementById('filter-mode').value;
            await saveSettings();
        }

        async function toggleFacebook() {
            currentSettings.facebook_posting_enabled = document.getElementById('facebook-toggle').checked;
            await saveSettings();
        }

        async function saveSettings() {
            try {
                const res = await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentSettings) });
                if (res.ok) { showToast('Settings saved!', 'success'); renderSettings(); }
                else showToast('Failed to save', 'error');
            } catch { showToast('Error saving', 'error'); }
        }

        // ─── Tabs ───────────────────────────────────────
        function switchTab(name, btn) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.getElementById('tab-' + name).classList.add('active');
            btn.classList.add('active');
            if (name === 'activity') loadActivity();
            if (name === 'posts') loadPosts();
        }

        // ─── Toast ──────────────────────────────────────
        function showToast(msg, type = 'success') {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.className = 'toast ' + type + ' show';
            setTimeout(() => t.classList.remove('show'), 3000);
        }

        function escapeHtml(text) {
            const d = document.createElement('div');
            d.textContent = text;
            return d.innerHTML;
        }

        // ─── Enter key ─────────────────────────────────
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Enter') return;
            const t = e.target;
            if (t.id === 'tg-channel-input') addItem('telegram_sources', 'tg-channel-input');
            else if (t.id === 'x-account-input') addItem('x_accounts', 'x-account-input');
            else if (t.id === 'x-hashtag-input') addItem('x_hashtags', 'x-hashtag-input');
            else if (t.id === 'include-keyword-input') addItem('filter_include_keywords', 'include-keyword-input');
            else if (t.id === 'exclude-keyword-input') addItem('filter_exclude_keywords', 'exclude-keyword-input');
        });

        // ─── API Keys ──────────────────────────────────
        async function loadApiKeys() {
            try {
                const res = await fetch('/api/credentials');
                const d = await res.json();
                const map = {
                    TELEGRAM_API_ID: 'api-tg-api-id', TELEGRAM_API_HASH: 'api-tg-api-hash',
                    TELEGRAM_PHONE: 'api-tg-phone', TELEGRAM_BOT_TOKEN: 'api-tg-bot-token',
                    TELEGRAM_CHANNEL_ID: 'api-tg-channel-id', X_BEARER_TOKEN: 'api-x-bearer',
                    FACEBOOK_PAGE_ACCESS_TOKEN: 'api-fb-token', FACEBOOK_PAGE_ID: 'api-fb-page-id'
                };
                for (const [k, id] of Object.entries(map)) {
                    if (d[k]) document.getElementById(id).placeholder = d[k];
                }
            } catch(e) { console.error(e); }
        }

        async function loadApiStatus() {
            const res = await fetch('/api/status');
            const d = await res.json();

            // Status overview
            const labels = { telegram_user: '📡 Telegram User', telegram_bot: '🤖 Telegram Bot', x_api: '𝕏  X API', facebook: '📘 Facebook' };
            document.getElementById('api-status').innerHTML = Object.entries(d).map(([k, ok]) => `
                <div class="setting-row">
                    <div class="setting-label">${labels[k] || k}</div>
                    <span style="font-size:0.78rem;font-weight:600;color:${ok ? 'var(--success)' : 'var(--error)'}">
                        ${ok ? '✓ Ready' : '✗ Not Set'}
                    </span>
                </div>
            `).join('');

            // Accordion badges
            const badgeMap = { telegram_user: 'badge-tg-user', telegram_bot: 'badge-tg-bot', x_api: 'badge-x', facebook: 'badge-fb' };
            for (const [k, id] of Object.entries(badgeMap)) {
                const el = document.getElementById(id);
                if (d[k]) { el.textContent = '✓ Ready'; el.className = 'accordion-badge ok'; }
                else { el.textContent = 'Not Set'; el.className = 'accordion-badge missing'; }
            }
        }

        async function saveApiKeys() {
            const fields = {
                'api-tg-api-id': 'TELEGRAM_API_ID', 'api-tg-api-hash': 'TELEGRAM_API_HASH',
                'api-tg-phone': 'TELEGRAM_PHONE', 'api-tg-bot-token': 'TELEGRAM_BOT_TOKEN',
                'api-tg-channel-id': 'TELEGRAM_CHANNEL_ID', 'api-x-bearer': 'X_BEARER_TOKEN',
                'api-fb-token': 'FACEBOOK_PAGE_ACCESS_TOKEN', 'api-fb-page-id': 'FACEBOOK_PAGE_ID',
            };
            const creds = {};
            for (const [id, k] of Object.entries(fields)) {
                const v = document.getElementById(id).value.trim();
                if (v) creds[k] = v;
            }
            if (!Object.keys(creds).length) { showToast('No new values to save', 'error'); return; }
            try {
                const res = await fetch('/api/credentials', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(creds) });
                if (res.ok) {
                    showToast('Saved & validated! Check Activity Log.', 'success');
                    Object.keys(fields).forEach(id => document.getElementById(id).value = '');
                    loadApiKeys(); loadApiStatus();
                    // Switch to Activity tab to show validation results
                    setTimeout(() => {
                        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
                        const activityTab = document.querySelectorAll('.tab')[3];
                        activityTab.classList.add('active');
                        document.getElementById('tab-activity').classList.add('active');
                        loadActivity();
                    }, 500);
                } else {
                    const e = await res.json();
                    showToast('Failed: ' + (e.error || 'Unknown'), 'error');
                }
            } catch { showToast('Error saving', 'error'); }
        }

        // ─── Init ───────────────────────────────────────
        loadSettings();
        loadStats();
        setInterval(loadStats, 30000);
        setInterval(loadActivity, 15000);
    </script>

</body>
</html>
"""


# ─── API Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(config.load_settings())


@app.route("/api/settings", methods=["POST"])
def post_settings():
    try:
        data = request.get_json()
        settings = config.update_settings(data)
        logger.info(f"⚙️  Settings updated via dashboard")
        return jsonify(settings)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats", methods=["GET"])
def api_stats():
    loop = asyncio.new_event_loop()
    try:
        stats = loop.run_until_complete(get_stats())
        return jsonify(stats)
    finally:
        loop.close()


@app.route("/api/activity", methods=["GET"])
def api_activity():
    loop = asyncio.new_event_loop()
    try:
        logs = loop.run_until_complete(get_activity_log())
        return jsonify(logs)
    finally:
        loop.close()


@app.route("/api/posts", methods=["GET"])
def api_posts():
    loop = asyncio.new_event_loop()
    try:
        posts = loop.run_until_complete(get_recent_posts())
        return jsonify(posts)
    finally:
        loop.close()


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(config.is_configured())


@app.route("/api/credentials", methods=["GET"])
def get_credentials():
    """Return masked API credentials to show what's configured."""
    env_path = config.BASE_DIR / ".env"
    values = {}
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if val and not val.startswith("your_"):
                    # Mask sensitive values
                    if len(val) > 8:
                        masked = val[:4] + "*" * (len(val) - 8) + val[-4:]
                    elif len(val) > 3:
                        masked = val[:2] + "*" * (len(val) - 2)
                    else:
                        masked = "***"
                    values[key] = masked
    return jsonify(values)


@app.route("/api/credentials", methods=["POST"])
def save_credentials():
    """Save API credentials to the .env file."""
    try:
        data = request.get_json()
        env_path = config.BASE_DIR / ".env"

        # Read existing .env content
        existing = {}
        lines = []
        if env_path.exists():
            with open(env_path, "r") as f:
                lines = f.readlines()
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _, val = stripped.partition("=")
                    existing[key.strip()] = val.strip()

        # Update with new values
        for key, val in data.items():
            existing[key] = val

        # Write .env file (preserving comments)
        new_lines = []
        written_keys = set()
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, _, _ = stripped.partition("=")
                key = key.strip()
                if key in existing:
                    new_lines.append(f"{key}={existing[key]}\n")
                    written_keys.add(key)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        # Append any new keys not in original file
        for key, val in existing.items():
            if key not in written_keys:
                new_lines.append(f"{key}={val}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        # Reload env vars into current process
        for key, val in data.items():
            os.environ[key] = val
        config.reload_env()

        # Log credential update to activity
        loop = asyncio.new_event_loop()
        try:
            from database import log_activity as db_log

            # Build friendly names for what was updated
            key_labels = {
                "TELEGRAM_API_ID": "Telegram API ID",
                "TELEGRAM_API_HASH": "Telegram API Hash",
                "TELEGRAM_PHONE": "Telegram Phone",
                "TELEGRAM_BOT_TOKEN": "Telegram Bot Token",
                "TELEGRAM_CHANNEL_ID": "Telegram Channel ID",
                "X_BEARER_TOKEN": "X Bearer Token",
                "FACEBOOK_PAGE_ACCESS_TOKEN": "Facebook Page Token",
                "FACEBOOK_PAGE_ID": "Facebook Page ID",
            }
            updated_names = [key_labels.get(k, k) for k in data.keys()]
            loop.run_until_complete(
                db_log("info", f"API credentials updated: {', '.join(updated_names)}", "dashboard")
            )

            # ─── Validate each API ───────────────────────────
            import requests as http_requests

            # Check Telegram User API
            if config.TELEGRAM_API_ID and config.TELEGRAM_API_HASH:
                try:
                    api_id = int(config.TELEGRAM_API_ID)
                    api_hash = config.TELEGRAM_API_HASH.strip()
                    errors = []
                    if api_id <= 0:
                        errors.append("API ID must be a positive number")
                    if len(api_hash) != 32:
                        errors.append(f"API Hash must be 32 characters (got {len(api_hash)})")
                    if not all(c in '0123456789abcdef' for c in api_hash):
                        errors.append("API Hash must contain only hex characters (0-9, a-f)")

                    if errors:
                        loop.run_until_complete(
                            db_log("error", f"❌ Telegram User API — {'; '.join(errors)}", "telegram")
                        )
                    else:
                        # Check if session file exists (meaning we've connected before)
                        import pathlib
                        session_file = pathlib.Path(config.BASE_DIR / f"{config.TELEGRAM_SESSION_NAME}.session")
                        if session_file.exists():
                            loop.run_until_complete(
                                db_log("info", "✅ Telegram User API — credentials valid, session exists (restart to connect)", "telegram")
                            )
                        else:
                            loop.run_until_complete(
                                db_log("info", "✅ Telegram User API — credentials format valid (restart to authenticate)", "telegram")
                            )
                except ValueError:
                    loop.run_until_complete(
                        db_log("error", "❌ Telegram User API — API ID must be a number", "telegram")
                    )
                except Exception as e:
                    loop.run_until_complete(
                        db_log("error", f"❌ Telegram User API — {e}", "telegram")
                    )
            else:
                loop.run_until_complete(
                    db_log("warning", "⚠️ Telegram User API — not configured (missing API ID or Hash)", "telegram")
                )

            # Check Telegram Bot
            if config.TELEGRAM_BOT_TOKEN:
                try:
                    resp = http_requests.get(
                        f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getMe",
                        timeout=10
                    )
                    bot_data = resp.json()
                    if bot_data.get("ok"):
                        bot_name = bot_data["result"].get("first_name", "Unknown")
                        bot_username = bot_data["result"].get("username", "")
                        loop.run_until_complete(
                            db_log("info", f"✅ Telegram Bot — connected as @{bot_username} ({bot_name})", "telegram")
                        )
                    else:
                        loop.run_until_complete(
                            db_log("error", f"❌ Telegram Bot — invalid token: {bot_data.get('description', 'Unknown error')}", "telegram")
                        )
                except Exception as e:
                    loop.run_until_complete(
                        db_log("error", f"❌ Telegram Bot — connection failed: {e}", "telegram")
                    )
            elif "TELEGRAM_BOT_TOKEN" in data:
                loop.run_until_complete(
                    db_log("warning", "⚠️ Telegram Bot — token is empty", "telegram")
                )

            # Check Telegram Channel
            if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHANNEL_ID:
                try:
                    resp = http_requests.get(
                        f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getChat",
                        params={"chat_id": config.TELEGRAM_CHANNEL_ID},
                        timeout=10
                    )
                    chat_data = resp.json()
                    if chat_data.get("ok"):
                        chat_title = chat_data["result"].get("title", "Unknown")
                        loop.run_until_complete(
                            db_log("info", f"✅ Telegram Channel — connected to \"{chat_title}\"", "telegram")
                        )
                    else:
                        loop.run_until_complete(
                            db_log("error", f"❌ Telegram Channel — {chat_data.get('description', 'Bot cannot access channel')}", "telegram")
                        )
                except Exception as e:
                    loop.run_until_complete(
                        db_log("error", f"❌ Telegram Channel — check failed: {e}", "telegram")
                    )

            # Check X API
            if config.X_BEARER_TOKEN:
                try:
                    resp = http_requests.get(
                        "https://api.x.com/2/users/me",
                        headers={"Authorization": f"Bearer {config.X_BEARER_TOKEN}"},
                        timeout=10
                    )
                    if resp.status_code == 200:
                        loop.run_until_complete(
                            db_log("info", "✅ X (Twitter) API — bearer token is valid", "x")
                        )
                    elif resp.status_code == 401:
                        loop.run_until_complete(
                            db_log("error", "❌ X (Twitter) API — bearer token is invalid (401 Unauthorized)", "x")
                        )
                    elif resp.status_code == 403:
                        # 403 means token is valid but endpoint needs different access level
                        loop.run_until_complete(
                            db_log("info", "✅ X (Twitter) API — bearer token accepted (some endpoints may need elevated access)", "x")
                        )
                    else:
                        loop.run_until_complete(
                            db_log("warning", f"⚠️ X (Twitter) API — unexpected response: {resp.status_code}", "x")
                        )
                except Exception as e:
                    loop.run_until_complete(
                        db_log("error", f"❌ X (Twitter) API — connection failed: {e}", "x")
                    )
            elif "X_BEARER_TOKEN" in data:
                loop.run_until_complete(
                    db_log("warning", "⚠️ X (Twitter) API — bearer token is empty", "x")
                )

            # Check Facebook
            if config.FACEBOOK_PAGE_ACCESS_TOKEN and config.FACEBOOK_PAGE_ID:
                try:
                    resp = http_requests.get(
                        f"https://graph.facebook.com/{config.FACEBOOK_API_VERSION}/{config.FACEBOOK_PAGE_ID}",
                        params={"access_token": config.FACEBOOK_PAGE_ACCESS_TOKEN, "fields": "name,id"},
                        timeout=10
                    )
                    fb_data = resp.json()
                    if "name" in fb_data:
                        loop.run_until_complete(
                            db_log("info", f"✅ Facebook Page — connected to \"{fb_data['name']}\" (ID: {fb_data['id']})", "facebook")
                        )
                    elif "error" in fb_data:
                        err_msg = fb_data["error"].get("message", "Unknown error")
                        loop.run_until_complete(
                            db_log("error", f"❌ Facebook Page — {err_msg}", "facebook")
                        )
                    else:
                        loop.run_until_complete(
                            db_log("warning", f"⚠️ Facebook Page — unexpected response", "facebook")
                        )
                except Exception as e:
                    loop.run_until_complete(
                        db_log("error", f"❌ Facebook Page — connection failed: {e}", "facebook")
                    )
            elif "FACEBOOK_PAGE_ACCESS_TOKEN" in data or "FACEBOOK_PAGE_ID" in data:
                loop.run_until_complete(
                    db_log("warning", "⚠️ Facebook Page — missing token or page ID", "facebook")
                )

        finally:
            loop.close()

        logger.info(f"🔑 API credentials updated: {list(data.keys())}")
        return jsonify({"success": True, "updated": list(data.keys())})

    except Exception as e:
        logger.error(f"❌ Failed to save credentials: {e}")
        return jsonify({"error": str(e)}), 500


# ─── Start Dashboard ─────────────────────────────────────────────────────────

def run_dashboard():
    """Run the Flask dashboard in a separate thread."""
    app.run(
        host="0.0.0.0",
        port=config.DASHBOARD_PORT,
        debug=False,
        use_reloader=False,
    )


async def start_dashboard_async():
    """Start the dashboard in a background thread from async context."""
    thread = threading.Thread(target=run_dashboard, daemon=True)
    thread.start()
    logger.info(f"🌐 Dashboard started on http://localhost:{config.DASHBOARD_PORT}")
    # Keep the task alive
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    run_dashboard()
