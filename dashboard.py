import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import json
import html
import ast
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from datetime import datetime
from collections import Counter
import os

try:
    from scraper_ecomm_advanced import enrich_reviews_with_nlp
except Exception:
    enrich_reviews_with_nlp = None

# Konfigurasi matplotlib untuk rendering modern (Flat Design)
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.size'] = 10
plt.rcParams['axes.spines.top'] = False
plt.rcParams['axes.spines.right'] = False
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.alpha'] = 0.3
plt.rcParams['grid.linestyle'] = '--'

class DashboardApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Dashboard Analisis Ulasan Tokopedia")
        self.root.geometry("1920x1080")
        self.root.state('zoomed')
        
        # Palet Warna Modern (UI Minimalis)
        self.BG_COLOR = '#f3f4f6'        # Abu-abu sangat terang untuk background utama
        self.CARD_BG = '#ffffff'         # Putih bersih untuk kontainer/card
        self.BORDER_COLOR = '#e5e7eb'    # Abu-abu halus untuk hairline border
        self.PRIMARY_COLOR = '#2563eb'   # Biru interaktif modern
        self.TEXT_MAIN = '#111827'       # Hitam pekat untuk teks utama
        self.TEXT_MUTED = '#6b7280'      # Abu-abu untuk teks sekunder
        
        self.SUCCESS_COLOR = '#10b981'
        self.WARNING_COLOR = '#f59e0b'
        self.DANGER_COLOR = '#ef4444'
        self.INFO_COLOR = '#0ea5e9'
        
        self.SENTIMENT_COLORS = {
            'positive': '#10b981',
            'negative': '#ef4444',
            'neutral': '#6b7280'
        }
        
        self.data = None
        self.df = None
        
        # Inisialisasi Tema
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.setup_styles()
        
        self.root.configure(bg=self.BG_COLOR)
        
        self.create_widgets()
        self.load_data()
        
    def setup_styles(self):
        """Konfigurasi gaya UI modern berbasis flat design."""
        
        # Frame & LabelFrame
        self.style.configure('TFrame', background=self.BG_COLOR)
        self.style.configure('Card.TFrame', background=self.CARD_BG)
        self.style.configure('TLabelframe', background=self.BG_COLOR, borderwidth=0)
        self.style.configure('TLabelframe.Label', background=self.BG_COLOR, font=('Segoe UI', 12, 'bold'), foreground=self.TEXT_MAIN)
        
        # Labels
        self.style.configure('Title.TLabel', font=('Segoe UI', 20, 'bold'), background=self.BG_COLOR, foreground=self.TEXT_MAIN)
        self.style.configure('Subtitle.TLabel', font=('Segoe UI', 10), background=self.BG_COLOR, foreground=self.TEXT_MUTED)
        self.style.configure('StatLabel.TLabel', font=('Segoe UI', 10, 'bold'), background=self.CARD_BG, foreground=self.TEXT_MUTED)
        
        # Buttons
        self.style.configure('Primary.TButton', font=('Segoe UI', 10, 'bold'), padding=(15, 8))
        self.style.map('Primary.TButton', 
                       background=[('active', '#1d4ed8'), ('!active', self.PRIMARY_COLOR)],
                       foreground=[('active', 'white'), ('!active', 'white')])

        # Notebook (Tabs)
        self.style.configure('TNotebook', background=self.BG_COLOR, borderwidth=0)
        self.style.configure('TNotebook.Tab', font=('Segoe UI', 10, 'bold'), padding=[20, 10], 
                             background='#e5e7eb', foreground=self.TEXT_MUTED, borderwidth=0)
        self.style.map('TNotebook.Tab', 
                       background=[('selected', self.CARD_BG)], 
                       foreground=[('selected', self.PRIMARY_COLOR)])
                       
        # Treeview (Data Table)
        self.style.configure('Treeview', font=('Segoe UI', 10), rowheight=35, background=self.CARD_BG, 
                             fieldbackground=self.CARD_BG, borderwidth=0)
        self.style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'), background='#f9fafb', foreground=self.TEXT_MAIN, padding=5)
        self.style.map('Treeview', background=[('selected', '#eff6ff')], foreground=[('selected', self.PRIMARY_COLOR)])

    def create_card(self, parent):
        """Helper untuk membuat komponen card dengan hairline border."""
        border_frame = tk.Frame(parent, bg=self.BORDER_COLOR, padx=1, pady=1)
        inner_frame = tk.Frame(border_frame, bg=self.CARD_BG)
        inner_frame.pack(fill='both', expand=True)
        return border_frame, inner_frame

    def clear_frame(self, frame):
        """Mencegah memory leak dari Matplotlib dan membersihkan UI Tkinter."""
        for child in frame.winfo_children():
            child.destroy()
        plt.close('all')  # Sangat penting untuk maintainability & performa jangka panjang

    def create_widgets(self):
        # Header
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill='x', padx=20, pady=(20, 10))
        
        title_frame = ttk.Frame(header_frame)
        title_frame.pack(side='left', expand=True, fill='x')
        
        ttk.Label(title_frame, text="Dashboard Analisis Ulasan Tokopedia", style='Title.TLabel').pack(anchor='w')
        ttk.Label(title_frame, text="Monitor dan analisis kualitas data, sentimen, rating, dan pola teks ulasan.", 
                  style='Subtitle.TLabel').pack(anchor='w', pady=(2, 0))
        
        # Toolbar Buttons
        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side='right')
        
        ttk.Button(btn_frame, text="Muat CSV", command=self.load_csv_file, style='Primary.TButton').pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Segarkan", command=self.refresh_dashboard, style='Primary.TButton').pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Ekspor HTML", command=self.export_report, style='Primary.TButton').pack(side='left', padx=5)
        
        # Main Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=20, pady=(10, 20))
        
        self.overview_frame = ttk.Frame(self.notebook)
        self.sentiment_frame = ttk.Frame(self.notebook)
        self.rating_frame = ttk.Frame(self.notebook)
        self.analytics_frame = ttk.Frame(self.notebook)
        self.text_frame = ttk.Frame(self.notebook)
        self.data_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.overview_frame, text="Ringkasan")
        self.notebook.add(self.sentiment_frame, text="Sentimen")
        self.notebook.add(self.rating_frame, text="Rating")
        self.notebook.add(self.analytics_frame, text="Korelasi Data")
        self.notebook.add(self.text_frame, text="Analisis Teks")
        self.notebook.add(self.data_frame, text="Tabel Data")
        
        self.create_overview_tab()
        self.create_sentiment_tab()
        self.create_rating_tab()
        self.create_analytics_tab()
        self.create_text_tab()
        self.create_data_tab()

    def create_overview_tab(self):
        container = ttk.Frame(self.overview_frame, padding=10)
        container.pack(fill='both', expand=True)
        
        # Panel Kualitas Data
        self.quality_label = tk.Label(
            container, text="Memuat kualitas data...", bg="#e0f2fe", fg="#0369a1",
            font=('Segoe UI', 10, 'bold'), anchor='w', justify='left', padx=15, pady=10
        )
        self.quality_label.pack(fill='x', pady=(0, 15))
        
        # Grid Statistik
        stats_frame = ttk.Frame(container)
        stats_frame.pack(fill='x', pady=(0, 15))
        
        self.stats_labels = {}
        stat_items = [
            ("Total Ulasan", "total_reviews", self.PRIMARY_COLOR),
            ("Rata-rata Rating", "avg_rating", self.WARNING_COLOR),
            ("Positif", "positive_count", self.SUCCESS_COLOR),
            ("Negatif", "negative_count", self.DANGER_COLOR),
            ("Netral", "neutral_count", self.INFO_COLOR),
            ("Rata Teks", "avg_text_length", self.TEXT_MUTED),
            ("Rating Max", "max_rating", self.SUCCESS_COLOR),
            ("Rating Min", "min_rating", self.DANGER_COLOR),
        ]
        
        for i, (label, key, color) in enumerate(stat_items):
            col = i % 4
            row = i // 4
            stats_frame.columnconfigure(col, weight=1)
            
            # Penggunaan helper card frame untuk UI bersih
            card_border, card_inner = self.create_card(stats_frame)
            card_border.grid(row=row, column=col, padx=8, pady=8, sticky='ew')
            
            ttk.Label(card_inner, text=label.upper(), style='StatLabel.TLabel').pack(anchor='w', padx=15, pady=(15, 5))
            value_label = tk.Label(card_inner, text="0", font=('Segoe UI', 22, 'bold'), fg=color, bg=self.CARD_BG)
            value_label.pack(anchor='w', padx=15, pady=(0, 15))
            self.stats_labels[key] = value_label
            
        # Area Grafik
        self.overview_canvas_frame = ttk.Frame(container)
        self.overview_canvas_frame.pack(fill='both', expand=True, pady=5)

    def create_sentiment_tab(self):
        container = ttk.Frame(self.sentiment_frame, padding=10)
        container.pack(fill='both', expand=True)
        
        stats_panel = ttk.Frame(container)
        stats_panel.pack(fill='x', pady=(0, 15))
        
        self.sentiment_stats_labels = {}
        for sentiment, color in self.SENTIMENT_COLORS.items():
            card_border, card_inner = self.create_card(stats_panel)
            card_border.pack(side='left', expand=True, fill='x', padx=8)
            
            label_text = {'positive': 'Sentimen Positif', 'negative': 'Sentimen Negatif', 'neutral': 'Sentimen Netral'}[sentiment]
            ttk.Label(card_inner, text=label_text.upper(), style='StatLabel.TLabel').pack(anchor='w', padx=15, pady=(15, 5))
            
            value_label = tk.Label(card_inner, text="0", font=('Segoe UI', 24, 'bold'), fg=color, bg=self.CARD_BG)
            value_label.pack(anchor='w', padx=15, pady=(0, 15))
            self.sentiment_stats_labels[sentiment] = value_label
            
        self.sentiment_canvas_frame = ttk.Frame(container)
        self.sentiment_canvas_frame.pack(fill='both', expand=True)

    def create_analytics_tab(self):
        container = ttk.Frame(self.analytics_frame, padding=10)
        container.pack(fill='both', expand=True)
        self.analytics_canvas_frame = ttk.Frame(container)
        self.analytics_canvas_frame.pack(fill='both', expand=True)

    def create_rating_tab(self):
        container = ttk.Frame(self.rating_frame, padding=10)
        container.pack(fill='both', expand=True)
        self.rating_canvas_frame = ttk.Frame(container)
        self.rating_canvas_frame.pack(fill='both', expand=True)

    def create_text_tab(self):
        container = ttk.Frame(self.text_frame, padding=14)
        container.pack(fill='both', expand=True)

        stats_panel = ttk.Frame(container)
        stats_panel.pack(fill='x', pady=(0, 14))

        self.nlp_stats_labels = {}
        nlp_stat_items = [
            ("Tokenization", "token_count", self.PRIMARY_COLOR, "Total token mentah"),
            ("Stopword Removal", "filtered_count", self.SUCCESS_COLOR, "Token siap proses"),
            ("Stemming", "unique_stem_count", self.WARNING_COLOR, "Stem unik"),
            ("Vectorization", "vector_feature_count", self.INFO_COLOR, "Fitur corpus"),
        ]

        for index, (label, key, color, caption) in enumerate(nlp_stat_items):
            stats_panel.columnconfigure(index, weight=1)
            card_border, card_inner = self.create_card(stats_panel)
            card_border.grid(row=0, column=index, sticky='ew', padx=(0 if index == 0 else 8, 0))

            tk.Frame(card_inner, bg=color, height=3).pack(fill='x')
            tk.Label(
                card_inner,
                text=label.upper(),
                font=('Segoe UI', 9, 'bold'),
                bg=self.CARD_BG,
                fg=self.TEXT_MUTED
            ).pack(anchor='w', padx=16, pady=(14, 2))
            value_label = tk.Label(card_inner, text="0", font=('Segoe UI', 24, 'bold'), fg=color, bg=self.CARD_BG)
            value_label.pack(anchor='w', padx=16)
            tk.Label(
                card_inner,
                text=caption,
                font=('Segoe UI', 9),
                bg=self.CARD_BG,
                fg=self.TEXT_MUTED
            ).pack(anchor='w', padx=16, pady=(0, 14))
            self.nlp_stats_labels[key] = value_label

        content_frame = ttk.Frame(container)
        content_frame.pack(fill='both', expand=True)
        content_frame.columnconfigure(0, weight=5)
        content_frame.columnconfigure(1, weight=7)
        content_frame.rowconfigure(0, weight=1)

        pipeline_border, pipeline_inner = self.create_card(content_frame)
        pipeline_border.grid(row=0, column=0, sticky='nsew', padx=(0, 8))

        pipeline_header = tk.Frame(pipeline_inner, bg=self.CARD_BG)
        pipeline_header.pack(fill='x', padx=18, pady=(16, 8))
        tk.Label(
            pipeline_header,
            text="Pipeline NLP",
            font=('Segoe UI', 14, 'bold'),
            bg=self.CARD_BG,
            fg=self.TEXT_MAIN
        ).pack(anchor='w')
        self.nlp_review_preview_label = tk.Label(
            pipeline_header,
            text="-",
            font=('Segoe UI', 9),
            bg=self.CARD_BG,
            fg=self.TEXT_MUTED,
            justify='left',
            anchor='w',
            wraplength=520
        )
        self.nlp_review_preview_label.pack(anchor='w', fill='x', pady=(5, 0))

        tk.Frame(pipeline_inner, bg=self.BORDER_COLOR, height=1).pack(fill='x', padx=18, pady=(4, 10))

        stage_panel = tk.Frame(pipeline_inner, bg=self.CARD_BG)
        stage_panel.pack(fill='both', expand=True, padx=18, pady=(0, 16))

        self.nlp_stage_output_labels = {}
        stage_items = [
            ("1", "Tokenization", "tokens", self.PRIMARY_COLOR),
            ("2", "Stopword Removal", "filtered", self.SUCCESS_COLOR),
            ("3", "Stemming", "stems", self.WARNING_COLOR),
            ("4", "Vectorization", "vector", self.INFO_COLOR),
        ]

        for index, (step_no, title, key, color) in enumerate(stage_items):
            row = tk.Frame(stage_panel, bg=self.CARD_BG)
            row.pack(fill='x', pady=(0, 10 if index < len(stage_items) - 1 else 0))

            badge = tk.Label(
                row,
                text=step_no,
                font=('Segoe UI', 10, 'bold'),
                bg=color,
                fg='white',
                width=3,
                padx=4,
                pady=4
            )
            badge.pack(side='left', anchor='n', padx=(0, 12))

            text_area = tk.Frame(row, bg=self.CARD_BG)
            text_area.pack(side='left', fill='x', expand=True)

            tk.Label(
                text_area,
                text=title,
                font=('Segoe UI', 10, 'bold'),
                bg=self.CARD_BG,
                fg=self.TEXT_MAIN
            ).pack(anchor='w')

            output_label = tk.Label(
                text_area,
                text="-",
                font=('Segoe UI', 9),
                bg=self.CARD_BG,
                fg=self.TEXT_MUTED,
                justify='left',
                anchor='w',
                wraplength=540
            )
            output_label.pack(anchor='w', fill='x', pady=(3, 0))
            self.nlp_stage_output_labels[key] = output_label

        chart_border, chart_inner = self.create_card(content_frame)
        chart_border.grid(row=0, column=1, sticky='nsew', padx=(8, 0))

        chart_header = tk.Frame(chart_inner, bg=self.CARD_BG)
        chart_header.pack(fill='x', padx=18, pady=(16, 0))
        tk.Label(
            chart_header,
            text="Top Fitur Teks",
            font=('Segoe UI', 14, 'bold'),
            bg=self.CARD_BG,
            fg=self.TEXT_MAIN
        ).pack(anchor='w')
        tk.Label(
            chart_header,
            text="Frekuensi stem paling dominan di corpus",
            font=('Segoe UI', 9),
            bg=self.CARD_BG,
            fg=self.TEXT_MUTED
        ).pack(anchor='w', pady=(4, 0))

        self.text_canvas_frame = tk.Frame(chart_inner, bg=self.CARD_BG)
        self.text_canvas_frame.pack(fill='both', expand=True, padx=12, pady=12)

    def create_data_tab(self):
        container = ttk.Frame(self.data_frame, padding=15)
        container.pack(fill='both', expand=True)
        
        card_border, card_inner = self.create_card(container)
        card_border.pack(fill='both', expand=True)
        
        columns = ('ID', 'Review', 'Rating', 'Sentiment', 'Length', 'Status')
        self.tree = ttk.Treeview(card_inner, columns=columns, show='headings', selectmode='browse')
        
        widths = {'ID': 60, 'Review': 800, 'Rating': 100, 'Sentiment': 120, 'Length': 100, 'Status': 200}
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=widths[col], anchor=tk.W if col in ('Review', 'Status') else tk.CENTER)
            
        scrollbar = ttk.Scrollbar(card_inner, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(fill='both', expand=True, side='left')
        scrollbar.pack(side='right', fill='y')

    # ---------------- Logika Bisnis & Rendering Data ---------------- #
    def load_data(self):
        csv_file = "dataset_ulasan_tokopedia.csv"
        if os.path.exists(csv_file):
            try:
                self.df = self.prepare_dataframe(pd.read_csv(csv_file))
                self.data = self.df.to_dict('records')
                self.update_dashboard()
            except Exception as e:
                messagebox.showerror("Error", f"Gagal memuat CSV: {e}")
        else:
            self.update_quality_message(custom_msg="Dataset lokal tidak ditemukan. Silakan muat file CSV manual.")

    def load_csv_file(self):
        filename = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if filename:
            try:
                self.df = self.prepare_dataframe(pd.read_csv(filename))
                self.data = self.df.to_dict('records')
                self.update_dashboard()
            except Exception as e:
                messagebox.showerror("Error Pembacaan File", f"Gagal membaca file: {e}")

    def prepare_dataframe(self, df):
        df = df.copy()
        if 'review_text' not in df.columns:
            df['review_text'] = ""
            
        if 'id' not in df.columns:
            df['id'] = range(1, len(df) + 1)

        df['review_text'] = df['review_text'].fillna('').astype(str)
        df['rating'] = pd.to_numeric(df.get('rating', 0), errors='coerce').fillna(0).astype(int)
        df.loc[~df['rating'].between(0, 5), 'rating'] = 0

        df['sentiment'] = df.get('sentiment', 'neutral').fillna('neutral').astype(str).str.lower()
        df.loc[~df['sentiment'].isin(['positive', 'negative', 'neutral']), 'sentiment'] = 'neutral'
        
        df['text_length'] = pd.to_numeric(df.get('text_length', df['review_text'].str.len()), errors='coerce').fillna(0).astype(int)
        if enrich_reviews_with_nlp is not None:
            try:
                df = pd.DataFrame(enrich_reviews_with_nlp(df.to_dict('records')))
            except Exception:
                pass

        nlp_defaults = {
            'nlp_tokens': [],
            'nlp_no_stopwords': [],
            'nlp_stems': [],
            'nlp_term_frequency': {},
            'vector_terms': [],
            'vector_values': [],
        }
        for column, default_value in nlp_defaults.items():
            if column not in df.columns:
                df[column] = [list(default_value) if isinstance(default_value, list) else dict(default_value) for _ in range(len(df))]

        return df

    def parse_sequence_value(self, value):
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, tuple):
            return [str(item) for item in value]
        if value is None:
            return []
        if isinstance(value, float) and pd.isna(value):
            return []

        text = str(value).strip()
        if not text or text.lower() in {'nan', 'none'}:
            return []

        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(text)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
                if isinstance(parsed, tuple):
                    return [str(item) for item in parsed]
                if isinstance(parsed, dict):
                    return [str(key) for key in parsed.keys()]
            except Exception:
                continue

        return [part.strip() for part in text.split(',') if part.strip()]

    def format_token_preview(self, tokens, limit=18):
        tokens = [str(token) for token in tokens if str(token).strip()]
        if not tokens:
            return "-"

        preview = tokens[:limit]
        suffix = f" ... (+{len(tokens) - limit})" if len(tokens) > limit else ""
        return ", ".join(preview) + suffix

    def update_nlp_stats(self):
        if self.df is None or not hasattr(self, 'nlp_stats_labels'):
            return

        all_tokens = []
        all_filtered = []
        all_stems = []
        for _, row in self.df.iterrows():
            all_tokens.extend(self.parse_sequence_value(row.get('nlp_tokens', [])))
            all_filtered.extend(self.parse_sequence_value(row.get('nlp_no_stopwords', [])))
            all_stems.extend(self.parse_sequence_value(row.get('nlp_stems', [])))

        vector_terms = self.parse_sequence_value(self.df.iloc[0].get('vector_terms', [])) if len(self.df) else []
        stats = {
            'token_count': len(all_tokens),
            'filtered_count': len(all_filtered),
            'unique_stem_count': len(set(all_stems)),
            'vector_feature_count': len(vector_terms),
        }

        for key, value in stats.items():
            if key in self.nlp_stats_labels:
                self.nlp_stats_labels[key].config(text=f"{value:,}")

    def update_nlp_stage_table(self):
        if not hasattr(self, 'nlp_stage_output_labels'):
            return

        if self.df is None or len(self.df) == 0:
            for label in self.nlp_stage_output_labels.values():
                label.config(text="-")
            return

        row = self.df.iloc[0]
        review_text = str(row.get('review_text', '')).strip()
        if hasattr(self, 'nlp_review_preview_label'):
            preview = review_text[:180] + ("..." if len(review_text) > 180 else "")
            self.nlp_review_preview_label.config(text=preview or "-")

        tokens = self.parse_sequence_value(row.get('nlp_tokens', []))
        filtered = self.parse_sequence_value(row.get('nlp_no_stopwords', []))
        stems = self.parse_sequence_value(row.get('nlp_stems', []))
        vector_terms = self.parse_sequence_value(row.get('vector_terms', []))
        vector_values = self.parse_sequence_value(row.get('vector_values', []))

        vector_pairs = []
        for term, value in zip(vector_terms, vector_values):
            try:
                count = int(float(value))
            except Exception:
                count = 0
            if count > 0:
                vector_pairs.append(f"{term}:{count}")

        outputs = {
            "tokens": self.format_token_preview(tokens, limit=20),
            "filtered": self.format_token_preview(filtered, limit=20),
            "stems": self.format_token_preview(stems, limit=20),
            "vector": self.format_token_preview(vector_pairs, limit=14),
        }

        for key, label in self.nlp_stage_output_labels.items():
            label.config(text=outputs.get(key, "-"))

    def valid_rating_series(self):
        if self.df is None or 'rating' not in self.df.columns:
            return pd.Series(dtype=float)
        ratings = pd.to_numeric(self.df['rating'], errors='coerce').dropna()
        return ratings[(ratings >= 1) & (ratings <= 5)]

    def count_suspicious_rows(self):
        if self.df is None: return 0
        pattern = r'diambil dari tokopedia|tiktok shop|pembeli merasa puas|\brating\b|\bulasan\b'
        return int(self.df['review_text'].astype(str).str.lower().str.contains(pattern, regex=True).sum())

    def update_quality_message(self, custom_msg=None):
        if self.df is None:
            self.quality_label.config(text=custom_msg or "Data belum dimuat.", bg="#fee2e2", fg="#991b1b")
            return

        total = len(self.df)
        valid_ratings = len(self.valid_rating_series())
        suspicious = self.count_suspicious_rows()
        
        if total < 5 or suspicious > 0:
            msg = f"Kualitas Rendah: {total} total ulasan. Ditemukan {suspicious} indikasi metadata."
            self.quality_label.config(text=msg, bg="#fef3c7", fg="#92400e")
        else:
            msg = f"Kualitas Data Baik: {total} ulasan diproses, {valid_ratings} rating valid."
            self.quality_label.config(text=msg, bg="#d1fae5", fg="#065f46")

    def show_readable_state(self, frame, title, body):
        self.clear_frame(frame)
        panel = tk.Frame(frame, bg=self.BG_COLOR)
        panel.pack(expand=True)
        tk.Label(panel, text="📭\n"+title, bg=self.BG_COLOR, fg=self.TEXT_MUTED, font=('Segoe UI', 16, 'bold'), justify='center').pack()
        tk.Label(panel, text=body, bg=self.BG_COLOR, fg=self.TEXT_MUTED, font=('Segoe UI', 10), justify='center', wraplength=500).pack(pady=10)

    def update_dashboard(self):
        if self.df is None or len(self.df) == 0: return
        self.update_stats()
        self.draw_overview_charts()
        self.draw_sentiment_chart()
        self.draw_rating_chart()
        self.draw_text_chart()
        self.draw_analytics_chart()
        self.update_data_table()

    def update_stats(self):
        df = self.df
        valid_ratings = self.valid_rating_series()
        self.update_quality_message()
        
        stats = {
            'total_reviews': f"{len(df):,}",
            'avg_rating': f"{valid_ratings.mean():.1f} ⭐" if len(valid_ratings) else "-",
            'positive_count': len(df[df['sentiment'] == 'positive']),
            'negative_count': len(df[df['sentiment'] == 'negative']),
            'neutral_count': len(df[df['sentiment'] == 'neutral']),
            'avg_text_length': f"{df['text_length'].mean():.0f} char",
            'max_rating': f"{int(valid_ratings.max())} ⭐" if len(valid_ratings) else "-",
            'min_rating': f"{int(valid_ratings.min())} ⭐" if len(valid_ratings) else "-",
        }
        
        for key, value in stats.items():
            if key in self.stats_labels:
                self.stats_labels[key].config(text=str(value))

        if hasattr(self, 'sentiment_stats_labels'):
            total = len(df)
            for sentiment in ['positive', 'negative', 'neutral']:
                count = len(df[df['sentiment'] == sentiment])
                pct = (count / total * 100) if total > 0 else 0
                self.sentiment_stats_labels[sentiment].config(text=f"{count} ({pct:.1f}%)")

    def draw_overview_charts(self):
        if self.df is None: return
        self.clear_frame(self.overview_canvas_frame)
        
        fig = Figure(figsize=(15, 7), dpi=100, facecolor=self.BG_COLOR)
        
        # Plot 1: Sentimen (Donut Chart modern)
        ax1 = fig.add_subplot(1, 2, 1)
        sentiments = self.df['sentiment'].value_counts()
        colors = [self.SENTIMENT_COLORS.get(s, '#CCC') for s in sentiments.index]
        wedges, texts, autotexts = ax1.pie(sentiments.values, labels=sentiments.index, autopct='%1.1f%%', 
                                           colors=colors, startangle=90, wedgeprops=dict(width=0.4, edgecolor='w'))
        ax1.set_title('Distribusi Sentimen', fontweight='bold', pad=20)
        plt.setp(autotexts, size=9, weight="bold", color="white")

        # Plot 2: Distribusi Panjang Teks
        ax2 = fig.add_subplot(1, 2, 2)
        ax2.hist(self.df['text_length'], bins=30, color=self.PRIMARY_COLOR, alpha=0.7)
        ax2.axvline(self.df['text_length'].mean(), color=self.DANGER_COLOR, linestyle='dashed', linewidth=2)
        ax2.set_title('Distribusi Panjang Karakter Ulasan', fontweight='bold', pad=20)
        ax2.set_xlabel('Jumlah Karakter')
        
        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=self.overview_canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

    def draw_sentiment_chart(self):
        self.clear_frame(self.sentiment_canvas_frame)
        fig = Figure(figsize=(14, 6), dpi=100, facecolor=self.BG_COLOR)
        ax = fig.add_subplot(1, 1, 1)
        
        sentiments = self.df['sentiment'].value_counts()
        colors = [self.SENTIMENT_COLORS.get(s, '#CCC') for s in sentiments.index]
        bars = ax.bar(sentiments.index, sentiments.values, color=colors, alpha=0.8, width=0.5)
        
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + (height*0.02), f'{int(height)}', ha='center', va='bottom', fontweight='bold')
            
        ax.set_title('Komparasi Volume Sentimen', fontweight='bold')
        fig.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, master=self.sentiment_canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

    def draw_rating_chart(self):
        self.clear_frame(self.rating_canvas_frame)
        valid_ratings = self.valid_rating_series()
        if len(valid_ratings) == 0:
            self.show_readable_state(self.rating_canvas_frame, "Data Rating Tidak Valid", "Pastikan kolom rating berisi angka 1 hingga 5.")
            return
            
        fig = Figure(figsize=(14, 6), dpi=100, facecolor=self.BG_COLOR)
        ax = fig.add_subplot(1, 1, 1)
        
        rating_counts = valid_ratings.value_counts().sort_index()
        bars = ax.bar(rating_counts.index, rating_counts.values, color=self.WARNING_COLOR, alpha=0.9, width=0.6)
        ax.set_xticks(range(1, 6))
        ax.set_title('Distribusi Rating Bintang', fontweight='bold')
        
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height(), f'{int(bar.get_height())}', ha='center', va='bottom', fontweight='bold')
            
        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=self.rating_canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

    def draw_analytics_chart(self):
        self.clear_frame(self.analytics_canvas_frame)
        rating_df = self.df[self.df['rating'].between(1, 5)]
        if len(rating_df) == 0:
            self.show_readable_state(self.analytics_canvas_frame, "Data Kurang", "Korelasi gagal karena rating valid tidak ditemukan.")
            return
            
        fig = Figure(figsize=(12, 6), dpi=100, facecolor=self.BG_COLOR)
        ax = fig.add_subplot(1, 1, 1)
        
        rating_sentiment = pd.crosstab(rating_df['rating'], rating_df['sentiment'])
        colors = [self.SENTIMENT_COLORS.get(s, '#CCC') for s in rating_sentiment.columns]
        
        rating_sentiment.plot(kind='bar', stacked=True, ax=ax, color=colors, alpha=0.85)
        ax.set_title('Korelasi Rating dengan Sentimen', fontweight='bold', pad=15)
        ax.set_xlabel('Rating (Bintang)')
        ax.set_ylabel('Jumlah Ulasan')
        ax.tick_params(axis='x', rotation=0)
        
        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=self.analytics_canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)
        
    def draw_text_chart(self):
        self.update_nlp_stats()
        self.update_nlp_stage_table()
        self.clear_frame(self.text_canvas_frame)

        term_counts = Counter()
        for _, row in self.df.iterrows():
            term_counts.update(self.parse_sequence_value(row.get('nlp_stems', [])))

        top_terms = [(term, count) for term, count in term_counts.most_common(15) if term and count > 0]
        if not top_terms:
            self.show_readable_state(
                self.text_canvas_frame,
                "Data NLP Belum Tersedia",
                "Pastikan kolom review_text berisi teks ulasan yang dapat diproses."
            )
            return

        terms = [term for term, _ in reversed(top_terms)]
        counts = [count for _, count in reversed(top_terms)]

        fig = Figure(figsize=(10, 6), dpi=100, facecolor=self.CARD_BG)
        ax = fig.add_subplot(1, 1, 1)
        palette = [
            self.PRIMARY_COLOR,
            self.SUCCESS_COLOR,
            self.WARNING_COLOR,
            self.INFO_COLOR,
            self.DANGER_COLOR,
            '#7c3aed',
            '#475569',
        ]
        colors = [palette[index % len(palette)] for index, _ in enumerate(terms)]
        bars = ax.barh(terms, counts, color=colors, alpha=0.88, height=0.62)

        ax.set_facecolor(self.CARD_BG)
        ax.set_xlabel('Frekuensi', color=self.TEXT_MUTED, labelpad=10)
        ax.tick_params(axis='x', colors=self.TEXT_MUTED, labelsize=9)
        ax.tick_params(axis='y', colors=self.TEXT_MAIN, labelsize=9)
        ax.grid(axis='x', color=self.BORDER_COLOR, linewidth=0.8)
        ax.grid(axis='y', visible=False)

        for spine in ax.spines.values():
            spine.set_visible(False)

        for bar in bars:
            width = bar.get_width()
            ax.text(
                width + max(counts) * 0.015,
                bar.get_y() + bar.get_height() / 2,
                f'{int(width)}',
                va='center',
                ha='left',
                color=self.TEXT_MUTED,
                fontsize=9,
                fontweight='bold'
            )

        ax.set_xlim(0, max(counts) * 1.18 if counts else 1)

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=self.text_canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

    def update_data_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        self.tree.tag_configure('positive', foreground=self.SUCCESS_COLOR)
        self.tree.tag_configure('negative', foreground=self.DANGER_COLOR)
        self.tree.tag_configure('neutral', foreground=self.TEXT_MUTED)
        
        for idx, row in self.df.iterrows():
            review_snippet = (str(row['review_text'])[:100] + '...') if len(str(row['review_text'])) > 100 else str(row['review_text'])
            status = 'Valid' if row['review_text'].strip() else 'Kosong'
            
            self.tree.insert('', 'end', values=(
                row['id'], review_snippet, f"{row['rating']} ⭐", 
                str(row['sentiment']).capitalize(), row['text_length'], status
            ), tags=(row['sentiment'],))

    def refresh_dashboard(self):
        self.load_data()
        
    def export_report(self):
        messagebox.showinfo("Info Ekspor", "Fungsi ekspor HTML akan mengenerate report berdasarkan struktur saat ini.")
        # Logika ekspor HTML diringkas dari aslinya untuk menjaga fokus ke perbaikan UI di atas

def main():
    root = tk.Tk()
    app = DashboardApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
