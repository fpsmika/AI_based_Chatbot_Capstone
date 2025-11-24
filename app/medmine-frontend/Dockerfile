FROM node:20

WORKDIR /app

COPY package*.json ./

RUN npm install

# Rebuild native binaries for Linux
RUN npm rebuild esbuild

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]