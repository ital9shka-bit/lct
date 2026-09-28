FROM node:22-alpine AS build

WORKDIR /app
COPY prototype/package.json prototype/package-lock.json ./
RUN npm ci
COPY prototype/ ./
RUN npm run build

FROM nginx:1.29-alpine
COPY prototype/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/client /usr/share/nginx/html
EXPOSE 80
