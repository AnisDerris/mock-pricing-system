{ b = int($1*2)/2.0; c[b]++ }
END { for (k = 4.0; k <= 10.0; k += 0.5) printf "%.1f %d\n", k, c[k]+0 }
