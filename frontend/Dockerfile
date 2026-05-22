# Stage 1: Build the Angular app
FROM node:20 AS build
WORKDIR /app
COPY . .
RUN npm install
RUN npx ng build --configuration production

# Stage 2: Set up Nginx to serve the app
FROM nginx:alpine
# Adjust the path below to match your project name in the dist folder
COPY --from=build /app/dist/*/browser /usr/share/nginx/html
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080