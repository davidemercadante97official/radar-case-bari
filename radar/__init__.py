# Sul PC di casa usa i certificati di Windows (antivirus che filtrano HTTPS).
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass
