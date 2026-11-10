export function encodingRecords(doc: any, id: any): {
    category: any;
    series: any;
    values: {
        [k: string]: any;
    };
}[];
export function encodingTable(doc: any, id: any, records: any): {
    headers: any[];
    rows: any;
};
