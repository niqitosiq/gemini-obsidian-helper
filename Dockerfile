FROM node:20-alpine AS builder

WORKDIR /usr/src/app

COPY package*.json ./
COPY pnpm-lock.yaml ./

# Install pnpm
RUN npm install -g pnpm

# Install dependencies
RUN pnpm install

COPY . .

# Build the application
RUN pnpm run build

FROM node:20-alpine

WORKDIR /usr/src/app

# Set timezone
ENV TZ="Europe/Moscow"
RUN apk add --no-cache tzdata && \
    cp /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone

COPY --from=builder /usr/src/app/dist ./dist
COPY --from=builder /usr/src/app/node_modules ./node_modules
COPY package*.json ./
COPY pnpm-lock.yaml ./

# Create directories for volumes
RUN mkdir -p ./vault
RUN mkdir -p ./temp_audio

EXPOSE 3000

# Command to run the app
CMD ["node", "dist/main"] 