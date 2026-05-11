export type HeaderProps = {
    day: string;
    time: string;
    onSaveSchedule: () => void;
    /** Вне рабочих часов: затемнить весь экран, кроме времени и иконки часов */
    screenDimmed?: boolean;
};
