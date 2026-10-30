import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', '').replace('postgres://', 'postgresql+psycopg://', 1).replace('postgresql://', 'postgresql+psycopg://', 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'true').lower() == 'true'
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_REFRESH_EACH_REQUEST = False
    MAX_CONTENT_LENGTH = 16 * 1024
    TRUSTED_HOSTS = [h.strip() for h in os.getenv('TRUSTED_HOSTS', 'localhost,127.0.0.1').split(',')]
    TRUST_PROXY = os.getenv('TRUST_PROXY', 'false').lower() == 'true'
    PRODUCTION = os.getenv('APP_ENV') == 'production'
    DOCUMENT_STORAGE_BACKEND = os.getenv('DOCUMENT_STORAGE_BACKEND', 'local')
    DOCUMENT_LOCAL_ROOT = os.getenv('DOCUMENT_LOCAL_ROOT', '')
    DOCUMENT_LOCAL_PERSISTENT = os.getenv('DOCUMENT_LOCAL_PERSISTENT', 'false').lower() == 'true'
    DOCUMENT_MAX_BYTES = int(os.getenv('DOCUMENT_MAX_BYTES', str(8 * 1024 * 1024)))
    DOCUMENT_MAX_FILES = int(os.getenv('DOCUMENT_MAX_FILES', '5'))
    DOCUMENT_MAX_PIXELS = int(os.getenv('DOCUMENT_MAX_PIXELS', '40000000'))
    DOCUMENT_PREVIEW_EDGE = int(os.getenv('DOCUMENT_PREVIEW_EDGE', '2400'))
    DOCUMENT_S3_BUCKET = os.getenv('DOCUMENT_S3_BUCKET', '')
    DOCUMENT_S3_ENDPOINT = os.getenv('DOCUMENT_S3_ENDPOINT') or None
    DOCUMENT_S3_REGION = os.getenv('DOCUMENT_S3_REGION', 'us-east-1')
    DOCUMENT_S3_ACCESS_KEY = os.getenv('DOCUMENT_S3_ACCESS_KEY') or None
    DOCUMENT_S3_SECRET_KEY = os.getenv('DOCUMENT_S3_SECRET_KEY') or None
    DOCUMENT_S3_SSE = os.getenv('DOCUMENT_S3_SSE', 'AES256')
