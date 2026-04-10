/**
 * AODB Flight Autocomplete
 * Populates <datalist> elements with AODB flight numbers for a given date
 * and provides click-to-fill functionality for related form fields.
 */

(function () {
  /**
   * Initialize AODB flight autocomplete for inputs with data-aodb-autocomplete attribute.
   * Also provides "click-to-fill" buttons to pre-populate form fields from a flight.
   */
  async function initAodbAutocomplete() {
    // Populate datalists on page load
    const datalists = document.querySelectorAll('[data-aodb-datalist]');
    for (const dlist of datalists) {
      await populateFlightDatalist(dlist);
    }

    // Wire up flight selection buttons (.use-flight-btn)
    document.querySelectorAll('.use-flight-btn').forEach((btn) => {
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        const flight = btn.dataset.flight || '';
        const stand = btn.dataset.stand || '';
        if (flight) {
          const inp = document.querySelector('input[name="flight_number"]');
          if (inp) inp.value = flight;
        }
        if (stand) {
          const sel = document.querySelector('select[name="allocated_stand"]');
          if (sel) {
            for (let i = 0; i < sel.options.length; i++) {
              if (sel.options[i].value === stand) {
                sel.selectedIndex = i;
                break;
              }
            }
          }
        }
        // Auto-scroll to form
        const form = document.querySelector('[data-flight-form]');
        if (form) form.scrollIntoView({ behavior: 'smooth' });
      });
    });
  }

  /**
   * Fetch flights for a datalist and populate the <option> elements.
   */
  async function populateFlightDatalist(datalist) {
    const dateStr = datalist.dataset.aodbDate || new Date().toISOString().split('T')[0];
    const typeFilter = datalist.dataset.aodbType || 'all';

    try {
      const url = `/apron/api/flights?date=${dateStr}&type=${typeFilter}`;
      const resp = await fetch(url);
      if (!resp.ok) {
        console.warn(`Failed to fetch AODB flights: ${resp.status}`);
        return;
      }

      const flights = await resp.json();
      datalist.innerHTML = '';
      flights.forEach((f) => {
        const label = f.flight_number ? 
          `${f.flight_number} (${f.arr_or_dep} - ${f.airline || ''})` :
          '';
        if (label) {
          const opt = document.createElement('option');
          opt.value = f.flight_number;
          opt.label = label;
          datalist.appendChild(opt);
        }
      });
    } catch (err) {
      console.error('AODB datalist fetch error:', err);
    }
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAodbAutocomplete);
  } else {
    initAodbAutocomplete();
  }
})();
