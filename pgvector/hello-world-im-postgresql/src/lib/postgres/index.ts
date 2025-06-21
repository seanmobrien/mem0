
import postgres from 'postgres';


let _db: postgres.Sql<Record<string, unknown>> | undefined;

/**
 * Returns a singleton instance of the PostgreSQL client.
 * 
 * @template T - The shape of the records returned by the database queries.
 * @returns {postgres.Sql<T>} The PostgreSQL client instance.
 */
export const db = <T extends Record<string, unknown>>(): postgres.Sql<T> => {
  if (!_db) {
    const connectionString = `postgresql://${process.env.POSTGRES_USER ?? 'postgres'}:${process.env.POSTGRES_PASSWORD}@localhost/${process.env.DATABASE_NAME ?? 'postgres'}`.trim();
    const sanitizedConnectionString = connectionString.replace(/:(.*)@/, ':***@');
    console.log(`Creating new PostgreSQL database connection to ${sanitizedConnectionString}.`);
    const ret = postgres(connectionString, { ssl: 'verify-full', max: 3, debug: true });
    _db = ret;
  }  
  return _db as postgres.Sql<T>;
};


/**
 * Closes the PostgreSQL database connection if it is open.
 * 
 * @returns {Promise<void>} A promise that resolves when the connection is closed.
 * @throws {Error} If there is an issue closing the connection.
 * @example
 * ```typescript
 * import { closeDb } from './path/to/your/postgres/module';
 * closeDb()
 *  .then(() => console.log('Database connection closed.'))
 * .catch(err => console.error('Error closing database connection:', err));
 * ```
 * @remarks
 * This function is automatically registered to run on process exit using the `prexit` package.
 * It ensures that the database connection is properly closed when the application terminates.
 * * Note: The `prexit` package must be installed and configured in your project for this functionality to work.
 * @see {@link db} for obtaining the database client instance.
 */
export const closeDb = async (): Promise<void> => {
  if (_db) {
    console.log('Closing database connection.');
    await _db.end();
    _db = undefined;
    console.log('Database connection closed.');
  }
};
 
let isPrexitRegistered = false;
 
try{
  if (!isPrexitRegistered) {
    isPrexitRegistered = true;
    await (import('prexit')
      .then(x => x.default))
      .then(prexit => {
        prexit(async () => {
          await closeDb();
        });
    });  
    console.log('Prexit handler registered to close database connection on exit.');
  }
}
catch (error) {
  console.error('Error registering prexit handler:', error);
}