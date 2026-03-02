# Dockerfile for bank-management-system backend

FROM python:3.11-slim

# set working directory
WORKDIR /app

# environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install system dependencies (if any) and python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy application code
COPY . .

# collect static assets before starting
RUN python manage.py collectstatic --noinput

# default command
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
