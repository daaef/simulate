FROM node:20-alpine

WORKDIR /app

COPY web/package.json /app/package.json
RUN npm install

COPY web /app

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]

