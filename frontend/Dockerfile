FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
# 构建阶段需要 devDependencies（vite、vue-tsc 等），不加 --only=production
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]