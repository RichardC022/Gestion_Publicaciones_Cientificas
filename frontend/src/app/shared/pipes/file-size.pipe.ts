import { Pipe, PipeTransform } from '@angular/core';

/**
 * Convierte bytes a una unidad legible (B, KB, MB, GB) con formato en
 * español. Devuelve una cadena vacía para valores ausentes o no
 * numéricos, de modo que las plantillas no muestren "NaN MB".
 */
@Pipe({ name: 'fileSize' })
export class FileSizePipe implements PipeTransform {
  transform(value: number | null | undefined, decimals = 1): string {
    if (value === null || value === undefined || !Number.isFinite(value) || value < 0) {
      return '';
    }
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = value;
    let unit = 0;
    while (size >= 1024 && unit < units.length - 1) {
      size /= 1024;
      unit += 1;
    }
    const formatter = new Intl.NumberFormat('es', {
      minimumFractionDigits: 0,
      maximumFractionDigits: decimals,
    });
    return `${formatter.format(size)} ${units[unit]}`;
  }
}
