FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY headers.inc /etc/nginx/snippets/headers.inc
COPY index.html robots.txt sitemap.xml og.png favicon.png apple-touch-icon.png /usr/share/nginx/html/
COPY assets /usr/share/nginx/html/assets
