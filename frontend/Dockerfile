# Производственный образ фронтенда: сборка Vite + раздача статики nginx-ом
# с проксированием API на backend (same-origin, CORS не нужен).
# та же мажорная версия, что в CI и в dev-compose: прод не должен
# собираться на рантайме, который нигде не проверяется
FROM node:26-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
