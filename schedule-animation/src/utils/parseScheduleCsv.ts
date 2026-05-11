import type { AnimationScheduleItem } from '../types/schedule';

function parseCsvLine(line: string): string[] {
    const values: string[] = [];
    let currentValue = '';
    let isQuoted = false;

    for (const char of line) {
        if (char === '"') {
            isQuoted = !isQuoted;
        } else if (char === ',' && !isQuoted) {
            values.push(currentValue.trim());
            currentValue = '';
        } else {
            currentValue += char;
        }
    }

    values.push(currentValue.trim());

    return values;
}

function getValue(row: Record<string, string>, keys: string[]): string {
    return keys.map((key) => row[key]).find(Boolean) ?? '';
}

function getDayFromDate(date: string): number {
    const weekDay = new Date(date).getDay();

    return weekDay === 0 ? 7 : weekDay;
}

export function parseScheduleCsv(csv: string): AnimationScheduleItem[] {
    const lines = csv.trim().split(/\r?\n/);
    const [headerLine, ...dataLines] = lines;

    if (!headerLine) {
        return [];
    }

    const headers = parseCsvLine(headerLine);

    return dataLines.map((line) => {
        const values = parseCsvLine(line);
        const row = headers.reduce<Record<string, string>>((result, header, index) => {
            result[header] = values[index] ?? '';

            return result;
        }, {});

        const date = getValue(row, ['date', 'ds']);
        const employeeIds = getValue(row, ['employeeIds', 'employee_ids', 'employees'])
            .split(/[;|]/)
            .map((employeeId) => employeeId.trim())
            .filter(Boolean);

        return {
            date,
            hour: Number(getValue(row, ['hour', 'sale_hour'])),
            station: getValue(row, ['station', 'station_key']),
            employeeIds,
            expectedPeopleCount: Number(getValue(row, ['expectedPeopleCount', 'expected_people_count', 'people_count', 'guests'])),
            expectationIndicator: getValue(row, ['expectationIndicator', 'expectation_indicator']),
            day: Number(getValue(row, ['day', 'weekday'])) || getDayFromDate(date),
        };
    });
}
