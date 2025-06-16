import { NextRequest, NextResponse } from 'next/server';
import { db, closeDb } from '@/lib/postgres';

export async function GET(req: NextRequest) {
  try {
    const messages: Array<string> = [];
    let systemAvailable = false;
    let tablesAvailable: boolean | undefined = undefined;
    let records: number | undefined = undefined;    
    try{
      // see if we can pull a connection
      const sql = db();
      // Execute a simple query to check the database connection
      const result = await sql`SELECT NOW() AS current_time`;
      if (result.length === 0) {
        throw new Error('System-level database query returned no results');
      }
      systemAvailable = true;
    } catch (error) {    
      if (!!error && typeof error === 'object' && 'message' in error) {
        messages.push(`Database connection error: ${error.message}`);
      } else { 
        messages.push(String(error));
      }
    }
    // If the system is available, optionally check for a table to be present
    if (systemAvailable && !req.nextUrl.searchParams.has('no-table')) {
      // If we have a table in our environment variables or were specifically asked for it, check for a count
      const tableName = (req.nextUrl.searchParams.get('table') ?? process.env.POSTGRES_CHECK_TABLE ?? '').trim();
      if (tableName) {
        try {
          const sql = db();
          const result = await sql`SELECT COUNT(*) AS count FROM ${sql(tableName)}`;
          if (result.length === 0 || !('count' in result[0])) {
            throw new Error(`Table ${tableName} does not exist or returned no results`);
          }
          records = result[0].count;
          messages.push(`Table ${tableName} exists with ${records} rows.`);
          tablesAvailable = true;
        } catch (error) {
          if (!!error && typeof error === 'object' && 'message' in error) {
            messages.push(`Table check error: ${error.message}`);
          } else {
            messages.push(String(error));
          }
          tablesAvailable = false;
        }
      }
    }
    const status = systemAvailable && tablesAvailable !== false ? 200 : 500;
    return NextResponse.json({
      systemAvailable,
      messages: messages.length > 0 ? messages : ['No issues detected'],
      ...(tablesAvailable !== undefined ? { 
        tablesAvailable,
        recordCount: records
      } : {}),
    }, { status, headers: { 'Content-Type': 'application/json' } });    
  }
  catch (error) {
    console.error('Error in status route:', error);
    return NextResponse.json({
      systemAvailable: false,
      messages: ['An unexpected error occurred while checking the database status.'],
    }, { status: 500, headers: { 'Content-Type': 'application/json' } });
  } finally {
    try{
      await closeDb();
    }catch(closeError) {
      console.error('Error closing database connection:', closeError);
    }
    console.log('Database connection closed after status check.');
  }
}
