declare function parseJson(input: string | null, filepath?: string): any;
declare function parseJson(input: string | null, reviver: (key: any, value: any) => any, filepath?: string): any;

export = parseJson;
