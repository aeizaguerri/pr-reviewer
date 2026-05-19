FROM node:22-alpine AS build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist/ /usr/share/nginx/html/

EXPOSE 80

CMD ["/bin/sh", "-c", "printf 'window.__PR_REVIEWER_CONFIG__ = { apiBaseUrl: \"%s\" };\n' \"${VITE_API_BASE_URL:-}\" > /usr/share/nginx/html/config.js && nginx -g 'daemon off;'"]
