# PostgreSQL Health Check Web Application

This is a lightweight [Next.js](https://nextjs.org) web application designed to monitor PostgreSQL database connectivity and availability. It's specifically built for containerized deployments and serverless environments where you need to verify database health.

## Purpose

This application serves as a simple health check monitor for PostgreSQL databases, particularly useful for:
- Container deployments with PostgreSQL
- Serverless applications that need database availability verification
- Development environments requiring quick database status checks
- Monitoring dashboards for database connectivity

## Features

- **Real-time Database Status**: Continuously monitors PostgreSQL connection health
- **Table Verification**: Optionally checks for specific table existence and record counts
- **Configurable Refresh Intervals**: Choose from 5 seconds to 10 minutes
- **Visual Status Indicators**: Color-coded display (green/red) for quick status assessment
- **Detailed Error Messages**: Shows specific connection or query errors
- **Responsive Design**: Works on desktop and mobile devices

## Getting Started

### Prerequisites

- Node.js 18+ 
- PostgreSQL database (local or remote)
- Environment variables configured (see Configuration section)

### Installation

```bash
npm install
# or
yarn install
# or 
pnpm install
```

### Configuration

Set the following environment variables:

```bash
# Required PostgreSQL connection details
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
DATABASE_NAME=your_database_name

# Optional: Table to check for existence and record count
POSTGRES_CHECK_TABLE=your_table_name
```

### Running the Application

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) to view the health check dashboard.

## API Endpoints

### GET /api/status

Returns JSON with database status information:

```json
{
  "systemAvailable": true,
  "tablesAvailable": true,
  "recordCount": 42,
  "messages": ["Table users exists with 42 rows."]
}
```

**Query Parameters:**
- `no-table`: Skip table existence checks
- `table`: Override the table name to check

## Docker Deployment

This application is designed to be easily containerized alongside PostgreSQL instances:

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

## Use Cases

1. **Container Health Checks**: Include in PostgreSQL containers to provide HTTP-based health endpoints
2. **Serverless Monitoring**: Deploy as a lightweight service to monitor database availability
3. **Development Tools**: Quick visual confirmation of database connectivity during development
4. **CI/CD Pipeline**: Use the `/api/status` endpoint for automated database availability testing

## Technology Stack

- **Frontend**: Next.js 15, React 19, TypeScript
- **Database**: PostgreSQL with `postgres` client library
- **Styling**: CSS Modules with responsive design
- **Deployment**: Optimized for containerized and serverless environments

## Learn More

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API
- [PostgreSQL Documentation](https://www.postgresql.org/docs/) - PostgreSQL database documentation
- [postgres Library](https://github.com/porsager/postgres) - The PostgreSQL client used