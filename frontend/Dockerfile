# Two targets, chosen by FRONTEND_TARGET in .env (docker-compose.yml):
#   dev  (default) - Vite dev server with live reload, behind Nginx TLS. For laptops.
#   prod           - the built app served as static files. For the shared server.
FROM node:20-alpine AS dev
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

FROM dev AS build
RUN npm run build

FROM nginx:1.27-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
# Same port as the dev server, so the edge Nginx config does not change. Unknown paths fall back to index.html
# because the app does its own routing (/employees/123, /audit, ...).
RUN printf '%s\n' \
  'server {' \
  '  listen 5173;' \
  '  root /usr/share/nginx/html;' \
  '  location /assets/ { expires 1y; add_header Cache-Control "public, immutable"; }' \
  '  location / { try_files $uri /index.html; add_header Cache-Control "no-cache"; }' \
  '}' > /etc/nginx/conf.d/default.conf
