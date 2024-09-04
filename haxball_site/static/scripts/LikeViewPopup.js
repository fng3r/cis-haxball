document.querySelectorAll('.popup-tab').forEach(popupTab => {
    let popupTabLike = popupTab.querySelector('.popup-tab-like');
    let popupTabDisLike = popupTab.querySelector('.popup-tab-dislike');


    popupTabLike.addEventListener("click", function(event) {
        let x = 0;
        if(event.target.parentElement.classList == "popup-tab-like"){
            x = event.target.parentElement.id;
        } else {
            x = event.target.id;
        }

        document.getElementById(x).style.boxShadow = '0px 0px 5px #00FF00';
        document.getElementById('dis' + x).style.boxShadow = '0px 0px 3px #fbd784';
        document.getElementById('vote-' + x).style.display = 'block';
        document.getElementById('vote-dis' + x).style.display = 'none';

    });

    popupTabDisLike.addEventListener("click", function(event){
        let x = 0;

        if(event.target.parentElement.classList == "popup-tab-dislike"){
            x = event.target.parentElement.id;
        } else {
            x = event.target.id;
        }

        x = x.replace('dis', '');

        document.getElementById(x).style.boxShadow = '0px 0px 3px #fbd784';
        document.getElementById('dis' + x).style.boxShadow = '0px 0px 5px #bd2130';
        document.getElementById('vote-' + x).style.display = 'none';
        document.getElementById('vote-dis' + x).style.display = 'block';

    });
});

