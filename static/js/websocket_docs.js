document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('search');
    const filterButtons = document.querySelectorAll('.filter-buttons button');
    const commandGroups = document.querySelectorAll('.command-group');

    let activeGroup = 'all';

    function filterCommands() {
        const searchTerm = searchInput.value.toLowerCase().trim();

        commandGroups.forEach(group => {
            const groupName = group.dataset.group;
            let groupHasVisible = false;

            const cards = group.querySelectorAll('.command-card');
            cards.forEach(card => {
                const commandName = card.dataset.command.toLowerCase();
                const commandDesc = (card.dataset.description || '').toLowerCase();
                const matchesSearch = searchTerm === '' ||
                    commandName.includes(searchTerm) ||
                    commandDesc.includes(searchTerm);

                const matchesGroup = activeGroup === 'all' || groupName === activeGroup;

                if (matchesSearch && matchesGroup) {
                    card.classList.remove('hidden');
                    groupHasVisible = true;
                } else {
                    card.classList.add('hidden');
                }
            });

            if (groupHasVisible && (activeGroup === 'all' || groupName === activeGroup)) {
                group.classList.remove('hidden');
            } else {
                group.classList.add('hidden');
            }
        });
    }

    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activeGroup = btn.dataset.group;
            filterCommands();
        });
    });

    searchInput.addEventListener('input', filterCommands);
});