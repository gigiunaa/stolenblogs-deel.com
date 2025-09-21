# ოფიციალური Python image
FROM python:3.11-slim

# სამუშაო დირექტორია
WORKDIR /app

# დააკოპირე ფაილები
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Gunicorn სერვერის გაშვება
CMD ["gunicorn", "-b", "0.0.0.0:5000", "blog_scraper_clean:app"]
