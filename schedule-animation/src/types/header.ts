export type HeaderProps = {
    /** 1 = пн … 7 = вс */
    activeDay: number;
    time: string;
    visitorsCount: number;
    onSelectDay: (day: number) => void;
};
