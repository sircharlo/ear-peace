# Frontend Dockerfile (build with Node, serve with Nginx)
FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Build-time variables to configure API URL and base path
ARG VITE_API_URL
ARG VITE_BASE
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_BASE=$VITE_BASE

RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
